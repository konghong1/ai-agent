from __future__ import annotations

import json
import re
import time

from fastapi import HTTPException
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langsmith import tracing_context
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal


from app.models import AgentConfig, AgentKnowledgeBase, KnowledgeBase, KBChunk, Message, Provider, ProviderModel, Thread, RetrievalLog
from app.services import new_thread_id, HybridRetriever, ContextBuilder, RAG_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT, KnowledgeBaseService
from app.settings import get_settings
from app.tools import get_tools

_BLOCKS_RE = re.compile(r"<blocks>(.*?)</blocks>", re.DOTALL)


def _extract_blocks(text: str) -> tuple[str, dict]:
    blocks: dict | None = None
    text_result = text
    match = _BLOCKS_RE.search(text)
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


def build_agent(agent_config: AgentConfig, user_id: int | None = None):
    """Build LLM using provider config if available, falling back to settings."""
    from app.models import Provider
    from sqlalchemy import select
    from app.core.database import SessionLocal

    settings = get_settings()
    api_key = settings.openai_api_key
    base_url = settings.openai_base_url
    model_name = agent_config.model_name or settings.openai_model

    if user_id:
        db = SessionLocal()
        try:
            # Try to find the default provider for this user
            provider = db.scalar(
                select(Provider).where(
                    Provider.user_id == user_id,
                    Provider.enabled == True,
                    Provider.is_default == True,
                )
            )
            if provider:
                api_key = provider.api_key or api_key
                base_url = provider.base_url or base_url
        finally:
            db.close()

    llm = ChatOpenAI(
        model=model_name,
        temperature=agent_config.temperature,
        api_key=api_key,
        base_url=base_url,
    )
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
            "content": f"\\n\\n<knowledge_context>\\n{rag_context}\\n</knowledge_context>\\n\\n请基于以上知识回答用户的问题。",
        })

    # Call Agent
    # Resolve provider/model
    chat_api_key = settings.openai_api_key
    chat_base_url = provider_base_url or settings.openai_base_url
    
    # If explicit model_name provided, use it; otherwise resolve from provider or agent
    resolved_model = model_name
    resolved_temperature = 0.7
    
    if not resolved_model and user_id:
        db2 = SessionLocal()
        try:
            # Try to find the specified provider first
            provider = None
            if provider_base_url:
                provider = db2.scalar(select(Provider).where(
                    Provider.user_id == user_id,
                    Provider.enabled == True,
                ).limit(1))
            
            if not provider:
                provider = db2.scalar(
                    select(Provider).where(
                        Provider.user_id == user_id, 
                        Provider.enabled == True, 
                        Provider.is_default == True,
                    )
                )
            
            if provider:
                chat_api_key = provider.api_key or chat_api_key
                if not resolved_model:
                    # Find default chat model for this provider
                    default_model = db2.scalar(select(ProviderModel).where(
                        ProviderModel.provider_id == provider.id,
                        ProviderModel.is_default_chat == True,
                        ProviderModel.model_type == "chat",
                        ProviderModel.enabled == True,
                    ))
                    if default_model:
                        resolved_model = default_model.model_name
                    elif provider.models:
                        resolved_model = next(
                            (m.model_name for m in provider.models if m.model_type == "chat" and m.enabled),
                            provider.models[0].model_name
                        )
        finally:
            db2.close()
    
    # Fallback to agent model name if still not resolved
    if not resolved_model and agent_config:
        resolved_model = agent_config.model_name or settings.openai_model
        resolved_temperature = agent_config.temperature
    
    if not resolved_model:
        resolved_model = settings.openai_model

    llm = ChatOpenAI(
        model=resolved_model,
        temperature=resolved_temperature,
        api_key=chat_api_key,
        base_url=chat_base_url,
    )
    agent_name = f"agent-{agent_config.id}" if agent_config else "chat"
    agent = create_agent(model=llm, tools=get_tools(), system_prompt="", name=agent_name)

    result = agent.invoke({"messages": langchain_messages})
    answer_raw = result["messages"][-1].content
    answer_text, blocks = _extract_blocks(answer_raw)

    msg = Message(
        thread_id=thread.id, role="assistant", content=answer_text,
        extra={"blocks": blocks, "retrieval": retrieval_info, "has_kb_context": rag_context is not None},
    )
    db.add(msg)
    db.commit()
    return answer_text, thread.id, blocks