from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

logger = logging.getLogger(__name__)

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.llm import LLMFactory, LLMConfig
from app.llm.openai_compat import OpenAICompatibleAdapter
from app.storage import inline_reference_image


from app.models import AgentConfig, AgentKnowledgeBase, KnowledgeBase, KBChunk, Message, Provider, ProviderModel, Thread, RetrievalLog
from app.services import new_thread_id, HybridRetriever, ContextBuilder, RAG_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT, KnowledgeBaseService
from app.settings import get_settings

_BLOCK_BLOCKS_RE = re.compile(r"<blocks>(.*?)</blocks>", re.DOTALL)


def _reference_images_to_blocks(reference_images: list[str] | None) -> list[dict]:
    """Convert reference-image references into OpenAI-style multimodal blocks.

    Each reference is inlined via :func:`app.storage.inline_reference_image`:
    ``data:`` URLs pass through, internal by-key proxy URLs (and any other
    local/private address) are fetched from object storage and inlined as
    base64 — the remote model cannot reach our private MinIO/proxy, so base64
    is the reliable path. External ``http(s)`` URLs are passed through as-is.
    """
    blocks: list[dict] = []
    for ref in (reference_images or [])[:8]:
        if not isinstance(ref, str):
            continue
        url = inline_reference_image(ref)
        if url is None:
            url = ref
        if url.startswith("data:") or url.startswith("http"):
            blocks.append({"type": "image_url", "image_url": {"url": url}})
    return blocks


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
    # Honor both OpenAI- and Agnes-style env naming. The deployment injects
    # AGNES_API_KEY / AGNES_BASE_URL into the container (not OPENAI_*), so the
    # chat/extraction LLM path must fall back to those — mirrors the convention
    # already used in app/gallery_prompt_ai.py for the gallery AI path.
    api_key = settings.openai_api_key or os.getenv("AGNES_API_KEY")
    base_url = settings.openai_base_url or os.getenv("AGNES_BASE_URL")
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
        resolved_model = os.getenv("AGNES_MODEL") or settings.openai_model
        # An Agnes endpoint won't have generic OpenAI model names — default to
        # the Agnes model when we're clearly pointed at one.
        if base_url and "agnes" in base_url and resolved_model == settings.openai_model:
            resolved_model = os.getenv("AGNES_MODEL", "agnes-2.0-flash")
    
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


def _make_chat_http_client(force_proxy: bool = False):
    """Proxy-resilient httpx client for the OpenAI-compatible chat client.

    Egress resilience strategy
    --------------------------
    The container is injected with ``HTTPS_PROXY=host.docker.internal:33210``
    (a host-side sandbox proxy). That proxy is *flaky* in some environments: a
    "half-dead" proxy accepts the TCP connect but never forwards, which hangs
    chat requests for 60-120s with no content. Direct egress to the LLM
    provider is verified working, so we go DIRECT by default and only use the
    proxy as a fallback (or when ``DISABLE_PROXY_AUTOFALLBACK=1`` mandates it).

    ``force_proxy=True`` returns a proxy-routed client — used by the one-shot
    retry after a direct attempt fails.
    """
    import httpx
    from app.http_client import _proxy_url, _proxy_reachable

    proxy = _proxy_url()

    # Mandatory-proxy mode: keep the original behaviour (proxy when present).
    if os.environ.get("DISABLE_PROXY_AUTOFALLBACK"):
        if proxy and _proxy_reachable():
            logging.getLogger(__name__).info("Chat client forced via egress proxy %s", proxy)
            return httpx.Client(proxy=proxy, timeout=120.0)
        return httpx.Client(timeout=120.0)

    if force_proxy and proxy:
        return httpx.Client(proxy=proxy, timeout=120.0)

    # Default: DIRECT. Do NOT read env proxy auto-detection (trust_env=False),
    # so a flaky/dead injected proxy can never hang the chat stream.
    return httpx.Client(trust_env=False, timeout=120.0)


def _create_llm_from_config(config: LLMConfig, force_proxy: bool = False):
    """Create an LLM instance (either via factory or legacy ChatOpenAI).

    ``force_proxy`` is forwarded to :func:`_make_chat_http_client`; see its
    docstring for the egress strategy. SDK-level ``max_retries`` adds resilience
    against transient 5xx / connection resets, and ``http_socket_options=()``
    suppresses langchain-openai's proxy-injection warning.
    """
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

    chat_client = _make_chat_http_client(force_proxy=force_proxy)

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
            http_client=chat_client,
            max_retries=2,
            http_socket_options=(),
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
            http_client=chat_client,
            max_retries=2,
            http_socket_options=(),
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

    thread = Thread(id=new_thread_id(), user_id=user_id, agent_id=agent_id, title=message[:5] or "新会话")
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
    reference_images: list[str] | None = None,
):
    """Run an agent turn.

    This is a **generator**: it yields streaming events
      ``("status", text)`` — progress hint (e.g. "正在调用工具查询实时数据…")
      ``("delta", text)``  — one incremental answer chunk
      ``("done", thread_id, blocks, full_text)`` — turn finished (assistant
        message already committed to ``db``)
    Callers that only need the final tuple should use :func:`ask_agent_sync`,
    which drains the generator and returns ``(answer_text, thread_id, blocks)``
    — keeping a single implementation for both streaming and non-streaming use.
    """
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

    # ── Resolve LLM config early (needed by ContextService summarizer) ──
    resolved_config = _resolve_llm_config(
        user_id=user_id,
        provider_id=provider_id,
        provider_base_url=provider_base_url,
        model_name=model_name,
        agent_config=agent_config,
        temperature=temperature,
    )
    if provider_type:
        resolved_config.provider_type = provider_type

    # ── Build messages: unified ContextService OR legacy full-history ──
    # 默认 enable_context_service=False → 走原全量加载，行为不变（后向兼容）。
    image_blocks = _reference_images_to_blocks(reference_images) if reference_images else []

    if getattr(settings, "enable_context_service", False):
        from app.context_service import ContextService, BuildOptions

        def _summarizer(text: str) -> str:
            from langchain_core.messages import HumanMessage, SystemMessage

            sum_llm = _create_llm_from_config(resolved_config)
            resp = sum_llm.invoke([
                SystemMessage(content=(
                    "将以下对话压缩为简洁中文摘要，保留：关键事实、用户明确表达的偏好/纠正、"
                    "未决事项与待办。不要编造未提及的信息。输出纯文本摘要。"
                )),
                HumanMessage(content=text),
            ])
            return resp.content or ""

        opts = BuildOptions(
            recent_turns=settings.context_service_recent_turns,
            reserved_reply_ratio=settings.context_service_reserved_reply_ratio,
            reflex_cap=settings.context_service_reflex_cap,
            recall_k=settings.context_service_recall_k,
            summarizer=_summarizer,
            enable_reflex=getattr(settings, "enable_retrieval_reflex", False),
            enable_memory_recall=getattr(settings, "enable_memory_recall", False),
            enable_gap_analysis=getattr(settings, "enable_gap_analysis", False),
            enable_rrf=getattr(settings, "enable_rrf", False),
        )
        cs = ContextService(db)
        langchain_messages = cs.build(
            thread=thread, user_id=user_id, current_text=message,
            system_prompt=system_prompt, opts=opts, model_name=resolved_config.model_name,
        )
        # 把参考图挂到当前用户轮（build 后最后一条 user 消息）
        if image_blocks:
            for _i in range(len(langchain_messages) - 1, -1, -1):
                if langchain_messages[_i]["role"] == "user":
                    _c = langchain_messages[_i]["content"]
                    langchain_messages[_i]["content"] = (
                        [{"type": "text", "text": _c}, *image_blocks] if isinstance(_c, str) else _c
                    )
                    break
    else:
        stored_messages = list(db.scalars(
            select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
        ))
        langchain_messages = [
            {"role": "system", "content": system_prompt or RAG_SYSTEM_PROMPT},
        ]
        last_user_idx = None
        for _i, _m in enumerate(stored_messages):
            if _m.role == "user":
                last_user_idx = _i

        for _i, msg in enumerate(stored_messages):
            if msg.role not in ("user", "assistant"):
                continue
            content = msg.content
            if msg.role == "user" and image_blocks and _i == last_user_idx:
                # Multimodal content: text first, then the attached images.
                content = [{"type": "text", "text": content}, *image_blocks]
            langchain_messages.append({"role": msg.role, "content": content})

    # Inject RAG context (两条路径共用)
    if rag_context:
        langchain_messages.append({
            "role": "user",
            "content": f"\n\n<knowledge_context>\n{rag_context}\n</knowledge_context>\n\n请基于以上知识回答用户的问题。",
        })

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

    # ── 扩展能力：Skill 目录 + MCP 工具 + Hook 生命周期（均受开关保护，默认关闭）──
    tools: list = []
    blocked_reason: str | None = None

    # Skill 目录（注入 system 上下文，让模型知道有哪些技能可用）
    skill_catalog = ""
    if getattr(settings, "enable_skill_tools", False):
        try:
            from app.skill_runtime import get_skill_catalog

            skill_catalog = get_skill_catalog(db, user_id)
        except Exception as e:
            logger.warning("Skill 目录加载失败（优雅降级）: %s", e)

    # Hook: UserPromptSubmit —— 用户提交消息时，可拦截或改写
    if getattr(settings, "enable_hooks", False):
        try:
            from app.hook_runner import run_hooks, first_blocking

            up = run_hooks("UserPromptSubmit", user_id, db,
                           {"session_id": thread.id, "prompt": message})
            blk = first_blocking(up)
            if blk:
                blocked_reason = f"消息被 Hook 拦截：{blk.reason}"
        except Exception as e:
            logger.warning("UserPromptSubmit Hook 执行失败（放行）: %s", e)

    if blocked_reason:
        answer_text, blocks = _extract_blocks(blocked_reason)
        db.add(Message(thread_id=thread.id, role="assistant", content=answer_text,
                       extra={"blocks": blocks, "hook_blocked": True}))
        db.commit()
        return answer_text, thread.id, blocks

    # 拼接 MCP + Skill 目录到 system 消息
    catalog_block = ""
    if getattr(settings, "enable_mcp_tools", False):
        try:
            from app.mcp_tools import get_mcp_tool_catalog

            catalog_block += get_mcp_tool_catalog(db, user_id)
        except Exception as e:
            logger.warning("MCP 目录加载失败（优雅降级）: %s", e)
    if skill_catalog:
        catalog_block += ("\n\n" + skill_catalog)
    if catalog_block:
        for _i, _m in enumerate(lc_messages):
            if isinstance(_m, SystemMessage):
                lc_messages[_i] = SystemMessage(content=(system_prompt or "") + "\n\n" + catalog_block)
                break

    # 构建工具集：MCP 远端工具 + use_skill
    if getattr(settings, "enable_mcp_tools", False):
        try:
            from app.mcp_tools import build_mcp_langchain_tools

            tools += build_mcp_langchain_tools(db, user_id)
        except Exception as e:
            logger.warning("MCP 工具加载失败（优雅降级）: %s", e)
    if getattr(settings, "enable_skill_tools", False):
        try:
            from app.skill_runtime import build_use_skill_tool

            us = build_use_skill_tool(db, user_id)
            if us:
                tools.append(us)
        except Exception as e:
            logger.warning("use_skill 工具加载失败（优雅降级）: %s", e)

    if tools:
        from langchain_core.messages import ToolMessage

        llm_with_tools = llm.bind_tools(tools)
        messages = list(lc_messages)
        answer_raw: str | None = None
        last_resp = None
        any_tool_called = False
        nudge_count = 0

        # ── Hook 封装（串行、DB 安全）──
        def _pre_hook(_tname, _targs):
            if not getattr(settings, "enable_hooks", False):
                return (False, "", _targs)
            try:
                from app.hook_runner import run_hooks, first_blocking

                pre = run_hooks("PreToolUse", user_id, db,
                                {"session_id": thread.id, "tool_name": _tname, "tool_args": _targs},
                                matcher=_tname)
                blk = first_blocking(pre)
                if blk:
                    return (True, blk.reason, _targs)
                mod = next((o for o in pre
                            if o.decision == "modify" and isinstance(o.data.get("tool_args"), dict)), None)
                if mod:
                    return (False, "", mod.data["tool_args"])
            except Exception as e:
                logger.warning("PreToolUse Hook 失败（放行）: %s", e)
            return (False, "", _targs)

        def _post_hook(_tname, _result):
            if not getattr(settings, "enable_hooks", False):
                return _result
            try:
                from app.hook_runner import run_hooks

                post = run_hooks("PostToolUse", user_id, db,
                                 {"session_id": thread.id, "tool_name": _tname, "tool_result": _result},
                                 matcher=_tname)
                mod = next((o for o in post
                            if o.decision == "modify" and "tool_result" in o.data), None)
                if mod:
                    return mod.data["tool_result"]
            except Exception as e:
                logger.warning("PostToolUse Hook 失败（保留原结果）: %s", e)
            return _result

        # 并行执行 MCP 工具（call_tool 内部用自带连接池，线程安全；不碰聊天 db 会话）
        def _exec_mcp(_tool, _targs):
            from app.mcp_client import MCPConnectionManager

            srv = getattr(_tool, "_mcp_server", None)
            mcp_name = getattr(_tool, "_mcp_tool_name", None) or _tool.name
            if srv is None:
                return f"[error] unknown MCP server for tool {_tool.name}"
            res, _lat, err = MCPConnectionManager.call_tool(user_id, srv, mcp_name, _targs)
            if err:
                return f"[MCP error] {err}"
            return res or ""

        for _step in range(getattr(settings, "mcp_max_iterations", 5)):
            try:
                resp = llm_with_tools.invoke(messages)
            except Exception as e:
                logger.warning("工具循环 LLM 调用失败: %s", e)
                answer_raw = None
                break
            last_resp = resp
            messages.append(resp)
            tool_calls = getattr(resp, "tool_calls", None) or []
            if tool_calls:
                any_tool_called = True
                yield ("status", "正在调用工具查询实时数据…")
                # 1) PreToolUse（串行）
                planned = []
                for tc in tool_calls:
                    tname = tc.get("name")
                    targs = tc.get("args", {}) or {}
                    blocked, reason, targs = _pre_hook(tname, targs)
                    planned.append((tc, tname, targs, blocked, reason))
                # 2) 并行执行：MCP 走 call_tool（线程安全）；非 MCP（如 use_skill）串行走 tool.func
                results: dict = {}
                mcp_jobs = []
                serial_jobs = []
                for (tc, tname, targs, blocked, reason) in planned:
                    if blocked:
                        results[tc.get("id")] = ("[blocked by hook] " + reason, tname)
                        continue
                    tool = next((t for t in tools if t.name == tname), None)
                    if tool and getattr(tool, "_mcp_server", None) is not None:
                        mcp_jobs.append((tc, tool, targs))
                    else:
                        serial_jobs.append((tc, tool, targs, tname))
                if mcp_jobs:
                    import concurrent.futures as _cf

                    _maxw = max(1, min(len(mcp_jobs), getattr(settings, "mcp_max_concurrency", 8) or 8))
                    with _cf.ThreadPoolExecutor(max_workers=_maxw) as ex:
                        fut_map = {ex.submit(_exec_mcp, tool, targs): tc for (tc, tool, targs) in mcp_jobs}
                        for fut in _cf.as_completed(fut_map):
                            tc = fut_map[fut]
                            try:
                                res = fut.result()
                            except Exception as _e:
                                res = f"[error] {_e}"
                            results[tc.get("id")] = (res, tc.get("name"))
                for (tc, tool, targs, tname) in serial_jobs:
                    try:
                        res = tool.func(**targs) if tool else f"[error] unknown tool: {tname}"
                    except Exception as _e:
                        res = f"[error] {_e}"
                    results[tc.get("id")] = (res, tname)
                # 3) PostToolUse（串行）+ 追加 ToolMessage
                for (tc, tname, targs, blocked, reason) in planned:
                    res, _ = results.get(tc.get("id"), ("", tname))
                    res = _post_hook(tname, res)
                    messages.append(ToolMessage(content=str(res), tool_call_id=tc.get("id")))
                # 工具已调用：携带结果继续循环，让模型整合答案
                continue
            # 本轮没有工具调用
            _text, _blk = _extract_blocks(resp.content or "")
            _is_stub = not _text.strip()
            if not any_tool_called and _is_stub and nudge_count < 2:
                # 模型未给出实质回答（空内容或仅 <blocks> 选择桩）且未调用任何工具：
                # 强制引导其使用 MCP 工具（最多两次，措辞逐步加强）。P2：强化首轮工具调用提示。
                nudge_count += 1
                if nudge_count == 1:
                    hint = (
                        "你没有调用任何工具，也没有给出实质性回答（只是返回了选项或空内容）。"
                        "如果用户的请求可以由已提供的 MCP 工具解答，你必须调用对应的 MCP 工具来获取真实数据，"
                        "不要凭空作答、不要返回选项桩、也不要反问用户如何选择。"
                        "⚠️ 你已被提供 MCP 工具，对于实时/数据类问题必须在第一轮就调用工具。"
                    )
                else:
                    hint = (
                        "再次强调：你当前必须调用一个已提供的 MCP 工具来回答用户的问题，"
                        "严禁再输出选项桩或空内容。先调用最匹配的 MCP 工具，再基于其返回的真实数据作答。"
                    )
                messages.append(HumanMessage(content=hint))
                continue
            # 最终回答：流式生成（P0）+ 状态事件
            yield ("status", "已获取实时数据，正在生成回答…")
            _full = []
            for chunk in llm.stream(messages):
                text = chunk.content if isinstance(chunk.content, str) else ""
                if text:
                    _full.append(text)
                    yield ("delta", text)
            answer_raw = "".join(_full)
            break
        if answer_raw is None:
            answer_raw = last_resp.content if last_resp is not None else ""
        # Stop Hook：响应生成后（informational，可改写最终答案）
        if getattr(settings, "enable_hooks", False):
            try:
                from app.hook_runner import run_hooks

                stop = run_hooks("Stop", user_id, db, {"session_id": thread.id, "answer": answer_raw})
                mod = next((o for o in stop if o.decision == "modify" and "answer" in o.data), None)
                if mod:
                    answer_raw = mod.data["answer"]
            except Exception as e:
                logger.warning("Stop Hook 失败（保留原答案）: %s", e)
    else:
        # 无工具：直接流式生成（P0）
        yield ("status", "正在生成回答…")
        _full = []
        for chunk in llm.stream(lc_messages):
            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                _full.append(text)
                yield ("delta", text)
        answer_raw = "".join(_full)

    answer_text, blocks = _extract_blocks(answer_raw)

    msg = Message(
        thread_id=thread.id, role="assistant", content=answer_text,
        extra={"blocks": blocks, "retrieval": retrieval_info, "has_kb_context": rag_context is not None},
    )
    db.add(msg)
    db.commit()

    # ── P5 隐式提取（默认关，后台线程，own session，不阻塞主链路）──
    if getattr(settings, "enable_implicit_extraction", False):
        _maybe_extract_memories(user_id, thread.id, resolved_config)

    # 作为生成器：以 done 事件收尾（同步调用方用 ask_agent_sync 抽取）
    yield ("done", thread.id, blocks, answer_text)


def ask_agent_sync(db, user_id, agent_id, message, **kwargs) -> tuple[str, str, dict]:
    """Drain :func:`ask_agent` (a generator) and return the final tuple.

    Used by the two non-streaming call sites (synchronous ``/chat`` and
    ``_run_text_chat``) so there is a single implementation shared with the
    streaming path. The assistant message is committed inside ``ask_agent``
    before the ``("done", ...)`` event, so by the time we return it is persisted.
    """
    last = None
    for ev in ask_agent(db, user_id, agent_id, message, **kwargs):
        if ev[0] == "done":
            last = ev
    if last is None:
        return "", None, {}
    # ev = ("done", thread_id, blocks, full_text) -> (answer_text, thread_id, blocks)
    return last[3], last[1], last[2]


def ask_agent_stream_gen(user_id, agent_id, message, thread_id, system_prompt, model_name,
                         provider_base_url, provider_type, provider_id, reference_images):
    """Streaming variant of :func:`ask_agent`.

    Yields tuples:
      ``("delta", text_chunk)``  — one incremental token/segment
      ``("done", thread_id, blocks, full_text)`` — generation finished
      ``("error", message)`` — unrecoverable error

    The function owns its OWN database session (same rationale as
    ``_run_text_chat``): a client disconnect that cancels the SSE generator can
    never close the session mid-commit, so user + assistant messages are always
    persisted even if the user switches pages mid-generation.

    Default simple chat path streams token-by-token via ``llm.stream()``.
    Complex paths (KB/RAG bindings, MCP/Skill tools, hooks, context-service)
    fall back to the battle-tested :func:`ask_agent` (non-stream) and emit the
    full answer as a single delta — correct, just not token-streamed.
    """
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        settings = get_settings()

        # Detect paths that ask_agent handles with extra machinery.
        agent_config = None
        if agent_id:
            agent_config = db.scalar(
                select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == user_id)
            )
        complex_path = bool(
            getattr(settings, "enable_mcp_tools", False)
            or getattr(settings, "enable_skill_tools", False)
            or getattr(settings, "enable_hooks", False)
            or getattr(settings, "enable_context_service", False)
            or (agent_config and getattr(agent_config, "knowledge_bases", None))
        )
        if complex_path:
            # P0：转发 ask_agent 生成器的流式事件（status / delta / done），
            # 不再把整段答案当一个 delta 一次性吐出。
            for ev in ask_agent(
                db=db, user_id=user_id, agent_id=agent_id, message=message,
                thread_id=thread_id, system_prompt=system_prompt, model_name=model_name,
                provider_base_url=provider_base_url, provider_type=provider_type,
                provider_id=provider_id, reference_images=reference_images,
            ):
                if ev[0] == "status":
                    yield ("status", ev[1])
                elif ev[0] == "delta":
                    yield ("delta", ev[1])
                elif ev[0] == "done":
                    yield ("done", ev[1], ev[2], ev[3])
            return

        # ── Simple default path: stream token-by-token ──
        if system_prompt is None:
            if agent_config and agent_config.system_prompt:
                system_prompt = agent_config.system_prompt
            else:
                system_prompt = DEFAULT_SYSTEM_PROMPT

        thread = _get_or_create_thread(db, user_id, agent_id, message, thread_id)
        db.add(Message(thread_id=thread.id, role="user", content=message))
        db.flush()

        resolved_config = _resolve_llm_config(
            user_id=user_id, provider_id=provider_id,
            provider_base_url=provider_base_url, model_name=model_name,
            agent_config=agent_config,
        )
        if provider_type:
            resolved_config.provider_type = provider_type

        # Legacy full-history build (same as ask_agent's default branch).
        stored_messages = list(db.scalars(
            select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
        ))
        lc_messages = [{"role": "system", "content": system_prompt or RAG_SYSTEM_PROMPT}]
        image_blocks = _reference_images_to_blocks(reference_images) if reference_images else []
        last_user_idx = None
        for _i, _m in enumerate(stored_messages):
            if _m.role == "user":
                last_user_idx = _i
        for _i, msg in enumerate(stored_messages):
            if msg.role not in ("user", "assistant"):
                continue
            content = msg.content
            if msg.role == "user" and image_blocks and _i == last_user_idx:
                content = [{"type": "text", "text": content}, *image_blocks]
            lc_messages.append({"role": msg.role, "content": content})

        llm = _create_llm_from_config(resolved_config)
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
        _lc = []
        for m in lc_messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "system":
                _lc.append(SystemMessage(content=content))
            elif role == "assistant":
                _lc.append(AIMessage(content=content))
            else:
                _lc.append(HumanMessage(content=content))

        def _stream_once(_llm, _msgs):
            """Stream one attempt; yields ('delta', text) and returns collected chunks."""
            collected: list[str] = []
            for chunk in _llm.stream(_msgs):
                text = chunk.content if isinstance(chunk.content, str) else ""
                if text:
                    collected.append(text)
                    yield ("delta", text)
            return collected

        full: list[str] = []
        try:
            full = yield from _stream_once(llm, _lc)
        except Exception as _stream_err:  # connectivity / transient failure
            # Direct egress is the reliable path in this deployment. Retry DIRECT
            # first (transient errors usually clear on a fresh connection); only
            # fall back to the injected proxy as a LAST resort for environments
            # where direct egress is genuinely blocked. Never route to the proxy
            # as the primary retry — the sandbox proxy is flaky and would just
            # hang the chat for 60-120s.
            logger.warning(
                "ask_agent_stream_gen: direct stream failed (%s); retrying direct once",
                _stream_err,
            )
            try:
                full = yield from _stream_once(_create_llm_from_config(resolved_config), _lc)
            except Exception:
                logger.warning("ask_agent_stream_gen: direct retry failed; trying proxy once")
                full = yield from _stream_once(
                    _create_llm_from_config(resolved_config, force_proxy=True), _lc
                )

        # Empty-response resume: agnes-2.0-flash occasionally returns no content
        # (the "no output" symptom). Retry DIRECT only — the injected proxy is
        # flaky and would only add latency, never recover an empty body.
        if not "".join(full).strip():
            logger.warning("ask_agent_stream_gen: empty stream response; retrying direct once")
            try:
                full = yield from _stream_once(_create_llm_from_config(resolved_config), _lc)
            except Exception as _empty_err:
                logger.error("ask_agent_stream_gen: empty-retry also failed: %s", _empty_err)

        answer_text, blocks = _extract_blocks("".join(full))
        db.add(Message(
            thread_id=thread.id, role="assistant", content=answer_text,
            extra={"blocks": blocks},
        ))
        db.commit()
        yield ("done", thread.id, blocks, "".join(full))
    except Exception as e:
        import traceback
        logger.error("ask_agent_stream_gen error: %s\n%s", e, traceback.format_exc())
        yield ("error", f"{type(e).__name__}: {e}")
    finally:
        db.close()


def _maybe_extract_memories(user_id: int, thread_id: str, resolved_config) -> None:
    """后台线程：从最近若干轮对话用 LLM 提取候选记忆 → pending 队列（需用户确认）。

    使用独立 SessionLocal（请求会话在 ask_agent 返回后即关闭）。默认关闭；
    隐式提取非零幻觉，必须经前端确认才落库，防记忆污染（多用户生产硬约束）。
    """
    def _job() -> None:
        try:
            from app.core.database import SessionLocal
            from app.memory import MemoryWriter
            from langchain_core.messages import HumanMessage, SystemMessage

            db2 = SessionLocal()
            try:
                recent = list(db2.scalars(
                    select(Message)
                    .where(Message.thread_id == thread_id)
                    .order_by(Message.created_at.desc())
                    .limit(12)
                ))
                convo = "\n".join(f"{m.role}: {m.content}" for m in reversed(recent))
                if not convo.strip():
                    return

                def _extractor(text: str) -> list[str]:
                    llm = _create_llm_from_config(resolved_config)
                    r = llm.invoke([
                        SystemMessage(content=(
                            "从对话中提取用户明确表达的偏好、事实或纠正。每条一行，"
                            "格式 'key: value'（如 '语言偏好: 简体中文'）。"
                            "只提取确凿表达的，不要推测。无则回复空行。"
                        )),
                        HumanMessage(content=text),
                    ])
                    return [ln.strip() for ln in (r.content or "").splitlines() if ln.strip()]

                MemoryWriter(db2).extract_candidates(user_id, convo, _extractor)
            finally:
                db2.close()
        except Exception as exc:
            logger.warning("implicit memory extraction skipped: %s", exc)

    threading.Thread(target=_job, name="mem-extract", daemon=True).start()
