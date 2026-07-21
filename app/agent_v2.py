"""
Integration Layer - Bridge between new agent_loop and existing system

Provides:
- ask_agent_v2_stream_gen: Generator that uses new agent_loop
- Tool registration for MCP/Skills
- Hook integration
"""

import logging
import os
import threading
import time
from typing import Generator

logger = logging.getLogger(__name__)

from app.core.database import SessionLocal
from app.hooks import trigger_hooks, load_user_hooks
from app.agent_loop import agent_loop, build_messages_from_history, TOOL_HANDLERS, register_tool_handler
from app.tool_pool import ToolPool, invalidate_tool_pool
from app.llm import LLMFactory, LLMConfig
from sqlalchemy import select


# ═══════════════════════════════════════════════════════════
#  LLM Adapter for agent_loop
# ═══════════════════════════════════════════════════════════

class LLMAdapter:
    """Adapter to make LLM compatible with agent_loop."""
    
    def __init__(self, llm):
        self.llm = llm
        self.stop_reason = None
    
    def invoke(self, messages: list, tools: list = None):
        """Invoke LLM with messages and optional tools."""
        # Convert messages to LLM format
        llm_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                llm_messages.append({"role": "system", "content": content})
            elif role == "user":
                llm_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                llm_messages.append({"role": "assistant", "content": content})
            # Skip tool messages for now (handled differently)
        
        # Invoke LLM
        response = self.llm.invoke(llm_messages)
        
        # Wrap response to have stop_reason
        class ResponseWrapper:
            def __init__(self, content, stop_reason="end_turn"):
                self.content = content
                self.stop_reason = stop_reason
                self.tool_calls = []
        
        return ResponseWrapper(response.content, "end_turn")


# ═══════════════════════════════════════════════════════════
#  Tool Handler Registration
# ═══════════════════════════════════════════════════════════

def register_builtin_tool_handlers():
    """Register built-in tool handlers."""
    from app.agent_loop import TOOL_HANDLERS
    
    # Bash tool
    def run_bash(command: str) -> str:
        import subprocess
        try:
            r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
            out = (r.stdout + r.stderr).strip()
            return out[:50000] if out else "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: Timeout (120s)"
    
    # Read file
    def run_read_file(path: str, limit: int = None) -> str:
        try:
            from pathlib import Path
            p = Path(path)
            if not p.exists():
                return f"Error: File not found: {path}"
            lines = p.read_text().splitlines()
            if limit and limit < len(lines):
                lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"
    
    # Write file
    def run_write_file(path: str, content: str) -> str:
        try:
            from pathlib import Path
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Wrote {len(content)} bytes to {path}"
        except Exception as e:
            return f"Error: {e}"
    
    # Register handlers
    TOOL_HANDLERS["bash"] = run_bash
    TOOL_HANDLERS["read_file"] = run_read_file
    TOOL_HANDLERS["write_file"] = run_write_file
    
    logger.info("Registered built-in tool handlers")


# ═══════════════════════════════════════════════════════════
#  V2 Agent Stream Generator
# ═══════════════════════════════════════════════════════════

def ask_agent_v2_stream_gen(
    user_id: int,
    agent_id: int | None,
    message: str,
    thread_id: str | None = None,
    system_prompt: str | None = None,
    model_name: str | None = None,
    provider_base_url: str | None = None,
    provider_type: str | None = None,
    provider_id: int | None = None,
    reference_images: list[str] | None = None,
    temperature: float | None = None,
) -> Generator[tuple[str, any], None, None]:
    """
    V2 Agent Stream Generator using new agent_loop.
    
    Replaces old architecture:
    - No unconditional RAG (model calls retrieve_knowledge tool)
    - No Intent Router (model decides path)
    - Tool Pool caching (MCP/Skills cached per user)
    - Hook integration at all extension points
    
    Yields:
        (event_type, event_data) tuples:
        - ("status", str): Progress message
        - ("delta", str): Text chunk
        - ("token_usage", dict): Token usage info
        - ("warning", str): Warning message
        - ("done", dict): Final response with thread_id
        - ("error", str): Error message
    """
    from app.agent import _resolve_llm_config
    from app.models import AgentConfig, Thread, Message
    from app.services import new_thread_id
    from app.settings import get_settings
    
    settings = get_settings()
    db = SessionLocal()
    
    try:
        # ── Step 1: UserPromptSubmit Hook ──
        trigger_hooks("UserPromptSubmit", message, user_id, agent_id)
        
        # Load user hooks from DB
        load_user_hooks(user_id, db)
        
        # ── Step 2: Resolve LLM config ──
        agent_config = None
        if agent_id:
            agent_config = db.get(AgentConfig, agent_id)
        
        llm_config = _resolve_llm_config(
            user_id=user_id,
            provider_id=provider_id,
            provider_base_url=provider_base_url,
            model_name=model_name,
            agent_config=agent_config,
            temperature=temperature,
        )
        
        # ── Step 3: Get or create thread ──
        thread = None
        if thread_id:
            thread = db.scalar(
                select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id)
            )
        
        if not thread:
            thread = Thread(id=new_thread_id(), user_id=user_id)
            db.add(thread)
            db.flush()
        
        # ── Step 4: Save user message ──
        user_msg = Message(
            thread_id=thread.id,
            role="user",
            content=message,
        )
        db.add(user_msg)
        db.flush()
        
        # ── Step 5: Build messages from history ──
        history_messages = list(db.scalars(
            select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
        ))
        
        history = [
            {"role": m.role, "content": m.content}
            for m in history_messages[:-1]  # Exclude current message
        ]
        
        # Resolve system prompt
        if not system_prompt and agent_config:
            system_prompt = agent_config.system_prompt
        if not system_prompt:
            system_prompt = "You are a helpful assistant."
        
        messages = build_messages_from_history(
            system_prompt=system_prompt,
            history=history,
            user_message=message,
            reference_images=reference_images,
        )
        
        # ── Step 6: Get tools from ToolPool ──
        tools = ToolPool.get_tools(user_id, db, agent_id)
        yield ("status", f"已加载 {len(tools)} 个工具")
        
        # ── Step 7: Create LLM adapter ──
        llm = LLMFactory.create(llm_config)
        llm_adapter = LLMAdapter(llm)
        
        # ── Step 8: Run agent_loop ──
        full_response = ""
        
        for event_type, event_data in agent_loop(
            messages=messages,
            tools=tools,
            llm=llm_adapter,
            user_id=user_id,
            agent_id=agent_id,
        ):
            yield (event_type, event_data)
            
            if event_type == "delta":
                full_response += event_data
        
        # ── Step 9: Save assistant message ──
        if full_response:
            assistant_msg = Message(
                thread_id=thread.id,
                role="assistant",
                content=full_response,
            )
            db.add(assistant_msg)
            db.flush()
        
        # ── Step 10: Yield done with thread_id ──
        yield ("done", {"thread_id": thread.id, "content": full_response})
        
        db.commit()
        
    except Exception as e:
        logger.error(f"ask_agent_v2_stream_gen failed: {e}", exc_info=True)
        yield ("error", str(e))
        db.rollback()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════
#  Initialization
# ═══════════════════════════════════════════════════════════

# Register tool handlers on module load
register_builtin_tool_handlers()


# ═══════════════════════════════════════════════════════════
#  API Integration Helper
# ═══════════════════════════════════════════════════════════

def should_use_v2_architecture() -> bool:
    """
    Check if V2 architecture should be used.
    
    Checks (in order):
    1. Environment variable USE_AGENT_V2
    2. Settings.use_agent_v2
    3. Default: False (use old architecture)
    """
    env = os.getenv("USE_AGENT_V2", "").lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    
    from app.settings import get_settings
    settings = get_settings()
    return getattr(settings, "use_agent_v2", False)
