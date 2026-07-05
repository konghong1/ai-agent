from __future__ import annotations

import json
import re
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.llm import LLMFactory, LLMConfig
from app.llm.openai_compat import OpenAICompatibleAdapter


from app.models import AgentConfig, AgentKnowledgeBase, KnowledgeBase, KBChunk, Message, Provider, ProviderModel, Thread, RetrievalLog
from app.services import new_thread_id, HybridRetriever, ContextBuilder, RAG_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT, KnowledgeBaseService
from app.settings import get_settings

_BLOCK_BLOCKS_RE = re.compile(r"<blocks>(.*?)</blocks>", re.DOTALL)


def _extract_blocks(text: str) -> tuple[str, dict]:
    blocks: dict | None = None
    text_result = text
    match = _BLOCK_BLOCKS_RE.search(text)
    if match:
        blocks_str = match.group(1)
        text_result = text[:match.start()] + text[match.end():]
        try:
            blocks = json.loads(blocks_str)
            if not isinstance(blocks, dict):
                blocks = None
        except (json.JSONDecodeError, ValueError):
            blocks = None
    return text_result.strip(), blocks or {}


def _resolve_llm_config(
    user_id: int | None,
    provider_id: int | None,
    provider_base_url: str | None,
    model_name: str | None,
    agent_config: AgentConfig | None,
    temperature: float | None = None,
    model_type: str = "chat",
) -> LLMConfig:
    """Resolve LLM configuration from various sources (provider, agent, settings).

    Resolution order:
    1. Explicit provider_id + model_name
    2. User's default provider
    3. Agent config
    4. Global settings
    """
    settings = get_settings()
    api_key = settings.openai_api_key
    base_url = settings.openai_base_url
    resolved_model = model_name
    resolved_temperature = temperature or (agent_config.temperature if agent_config else 0.7)

    if user_id:
        db = SessionLocal()
        try:
            # Try to find specific provider first
            provider = None
            if provider_id:
                provider = db.get(Provider, provider_id)
                provider = provider if provider and provider.user_id == user_id and provider.enabled else None
            
            if not provider and not provider_id:
                provider = db.scalar(
                    select(Provider).where(
                        Provider.user_id == user_id,
                        Provider.enabled == True,
                        Provider.is_default == True,
                    )
                )

            if provider:
                api_key = provider.api_key or api_key
                base_url = provider_base_url or provider.base_url or base_url
                
                if not resolved_model:
                    # Find default model for this provider matching the requested type
                    type_to_flag = {
                        "chat": ProviderModel.is_default_chat,
                        "image": ProviderModel.is_default_image,
                        "video": ProviderModel.is_default_video,
                        "embedding": ProviderModel.is_default_embedding,
                    }
                    flag = type_to_flag.get(model_type, ProviderModel.is_default_chat)
                    default_model = db.scalar(select(ProviderModel).where(
                        ProviderModel.provider_id == provider.id,
                        flag == True,
                        ProviderModel.model_type == model_type,
                        ProviderModel.enabled == True,
                    ))
                    if default_model:
                        resolved_model = default_model.model_name
                    elif provider.models:
                        matching = [m for m in provider.models if m.model_type == model_type and m.enabled]
                        resolved_model = matching[0].model_name if matching else None
        finally:
            db.close()

    # Fallback to agent model name if still not resolved
    if not resolved_model and agent_config:
        resolved_model = agent_config.model_name or settings.openai_model
        if temperature is None and resolved_temperature == 0.7:
            resolved_temperature = agent_config.temperature

    if not resolved_model:
        resolved_model = settings.openai_model
    
    # Determine provider_type based on base_url
    provider_type = "openai-compatible"  # default

    import logging as _llm_logging
    _llm_log = _llm_logging.getLogger(__name__)
    _llm_log.info(
        "Resolved LLM config: model=%s base_url=%s provider_type=%s api_key_prefix=%s",
        resolved_model, base_url, provider_type, (api_key or "")[:8] + "..." if api_key else "None"
    )

    return LLMConfig(
        provider_type=provider_type,
        model_name=resolved_model,
        api_key=api_key,
        base_url=base_url,
        temperature=resolved_temperature,
    )


def _create_llm_from_config(config: LLMConfig):
    """Create an LLM instance (either via factory or legacy ChatOpenAI)."""
    import logging
    _log = logging.getLogger(__name__)
    _log.info("Creating LLM — model=%s base_url=%s provider_type=%s api_key=%s...",
              config.model_name, config.base_url, config.provider_type,
              (config.api_key or "")[:8])
    
    # Keep OpenAI/httpx quiet — DEBUG produces huge volume of request logs
    _openai_log = logging.getLogger("openai")
    _openai_log.setLevel(logging.WARNING)
    _httpx_log = logging.getLogger("httpx")
    _httpx_log.setLevel(logging.WARNING)
    
    # Try factory first
    try:
        adapter = LLMFactory.create(config)
        # For now, ChatAgent still needs a langchain model, so we fall back to ChatOpenAI
        # but the adapter pattern is ready for future streaming use
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=config.api_key,
            base_url=config.base_url,
        )
    except Exception as e:
        _log.error("Factory create failed: %s, falling back to ChatOpenAI directly", e)
        # Fallback to direct ChatOpenAI
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=config.api_key,
            base_url=config.base_url,
        )


def build_agent(agent_config: AgentConfig, user_id: int | None = None):
    """Build LLM using provider config if available, falling back to settings."""
    # Lazy imports: only load langchain.agents (heavy) when actually building an agent
    from langchain.agents import create_agent
    from app.tools import get_tools

    config = _resolve_llm_config(
        user_id=user_id,
        provider_id=None,
        provider_base_url=None,
        model_name=agent_config.model_name,
        agent_config=agent_config,
        temperature=agent_config.temperature,
    )
    llm = _create_llm_from_config(config)
    return create_agent(
        model=llm,
        tools=get_tools(),
        system_prompt=agent_config.system_prompt,
        name=f"agent-{agent_config.id}",
    )


def _get_or_create_thread(db: Session, user_id: int, agent_id: int | None, message: str, thread_id: str | None) -> Thread:
    if thread_id:
        thread = db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id))
        if agent_id:
            thread = thread and thread.agent_id == agent_id and thread
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found.")
        return thread

    thread = Thread(id=new_thread_id(), user_id=user_id, agent_id=agent_id or 0, title=message[:60] or "New chat")
    db.add(thread)
    db.flush()
    return thread


def ask_agent(
    db: Session,
    user_id: int,
    agent_id: int | None,
    message: str,
    thread_id: str | None = None,
    system_prompt: str | None = None,
    model_name: str | None = None,
    provider_base_url: str | None = None,
    provider_type: str | None = None,
    provider_id: int | None = None,
    temperature: float | None = None,
) -> tuple[str, str, dict]:
    settings = get_settings()
    
    # If agent_id is provided and no system_prompt from template, load agent config
    agent_config = None
    if agent_id:
        agent_config = db.scalar(select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == user_id))
        if not agent_config:
            raise HTTPException(status_code=404, detail="Agent not found.")
        if not agent_config.enabled:
            raise HTTPException(status_code=400, detail="Agent is disabled.")
        if system_prompt is None:
            system_prompt = agent_config.system_prompt
    
    # If still no system_prompt, use default
    if system_prompt is None:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    thread = _get_or_create_thread(db, user_id, agent_id, message, thread_id)
    db.add(Message(thread_id=thread.id, role="user", content=message))
    db.flush()

    # === RAG Retrieval (if agent has KB bindings) ===
    rag_context = None
    retrieval_info = []
    bound_kb_ids = [kb.id for kb in (agent_config.knowledge_bases if agent_config else [])]

    if bound_kb_ids:
        start_time = time.time()
        all_hits = []
        for kb_id in bound_kb_ids:
            kb = db.get(KnowledgeBase, kb_id)
            if not kb or not kb.enabled:
                continue
            retriever = HybridRetriever(kb, db)
            hits = retriever.retrieve(
                query=message,
                top_k=kb.rag_config.get('top_k', 20),
                rerank_top_k=kb.rag_config.get('rerank_top_k', 10),
            )
            for h in hits:
                h['metadata']['kb_name'] = kb.name
            all_hits.extend(hits)

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Sort and deduplicate by score
        all_hits.sort(key=lambda x: x.get('score', 0), reverse=True)
        seen_ids = set()
        unique_hits = []
        for h in all_hits:
            if h['vector_id'] not in seen_ids:
                seen_ids.add(h['vector_id'])
                unique_hits.append(h)
        all_hits = unique_hits[:kb.rag_config.get('top_k', 5)]

        if all_hits:
            max_tokens = kb.rag_config.get('max_context_tokens', 4000)
            builder = ContextBuilder(max_tokens=max_tokens)
            rag_context, retrieval_info = builder.build(
                query=message,
                hits=all_hits,
                include_sources=kb.rag_config.get('include_sources', True),
            )

        # Log retrieval
        if retrieval_info:
            avg_score = sum(h.get('score', 0) for h in retrieval_info) / len(retrieval_info)
            log_entry = RetrievalLog(
                thread_id=thread.id,
                query=message,
                kb_id=bound_kb_ids[0],
                top_k=len(all_hits),
                hit_count=len(retrieval_info),
                avg_score=avg_score,
                took_ms=elapsed_ms,
            )
            db.add(log_entry)

    # Build messages
    stored_messages = list(db.scalars(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
    ))
    langchain_messages = [
        {"role": "system", "content": system_prompt or RAG_SYSTEM_PROMPT},
    ]
    for msg in stored_messages:
        if msg.role in ("user", "assistant"):
            langchain_messages.append({"role": msg.role, "content": msg.content})

    # Inject RAG context
    if rag_context:
        langchain_messages.append({
            "role": "user",
            "content": f"\n\n<knowledge_context>\n{rag_context}\n</knowledge_context>\n\n请基于以上知识回答用户的问题。",
        })

    # Resolve LLM config from provider/agent
    resolved_config = _resolve_llm_config(
        user_id=user_id,
        provider_id=provider_id,
        provider_base_url=provider_base_url,
        model_name=model_name,
        agent_config=agent_config,
        temperature=temperature,
    )
    
    # Override with explicit provider_type if provided
    if provider_type:
        resolved_config.provider_type = provider_type

    llm = _create_llm_from_config(resolved_config)

    # Convert dict messages to LangChain message objects for direct invoke
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    lc_messages = []
    for m in langchain_messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))

    response = llm.invoke(lc_messages)
    answer_raw = response.content
    answer_text, blocks = _extract_blocks(answer_raw)

    msg = Message(
        thread_id=thread.id, role="assistant", content=answer_text,
        extra={"blocks": blocks, "retrieval": retrieval_info, "has_kb_context": rag_context is not None},
    )
    db.add(msg)
    db.commit()
    return answer_text, thread.id, blocks
