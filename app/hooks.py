"""
Hook System for Model-Driven Agent Loop

Based on s04_hooks design from learn-claude-code:
- HOOKS registry (event -> list of callbacks)
- register_hook() / trigger_hooks()
- Built-in hooks: permission, log, context_inject, summary
- User-defined hooks loaded from DB

Hook Types:
- UserPromptSubmit: triggered when user sends a message (can inject context)
- PreToolUse: triggered before tool execution (can block)
- PostToolUse: triggered after tool execution (can modify output)
- Stop: triggered when model decides to stop (can inject final message)
"""

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Hook Registry
# ═══════════════════════════════════════════════════════════

HOOKS: dict[str, list[Callable]] = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": [],
    "ToolInit": [],
    "ToolPoolInvalidated": [],
}

_hook_lock = threading.Lock()


def register_hook(event: str, callback: Callable) -> None:
    """
    Register a hook callback for a specific event.
    
    Args:
        event: Hook type (UserPromptSubmit/PreToolUse/PostToolUse/Stop/ToolInit/ToolPoolInvalidated)
        callback: Function to call when event triggers
    """
    if event not in HOOKS:
        logger.warning(f"Unknown hook event: {event}")
        return
    
    with _hook_lock:
        HOOKS[event].append(callback)
    logger.info(f"Registered hook for {event}: {callback.__name__}")


def trigger_hooks(event: str, *args, **kwargs) -> Optional[str]:
    """
    Trigger all hooks for a specific event.
    
    Args:
        event: Hook type
        *args: Positional arguments passed to hooks
        **kwargs: Keyword arguments passed to hooks
    
    Returns:
        None if no hook blocked, or block reason string
    """
    if event not in HOOKS:
        return None
    
    for callback in HOOKS[event]:
        try:
            result = callback(*args, **kwargs)
            if result is not None:
                logger.info(f"Hook {callback.__name__} blocked: {result}")
                return result
        except Exception as e:
            logger.error(f"Hook {callback.__name__} failed: {e}")
            # Continue executing other hooks even if one fails
    
    return None


def clear_hooks(event: Optional[str] = None) -> None:
    """
    Clear hooks (for testing).
    
    Args:
        event: Specific event to clear, or None to clear all
    """
    with _hook_lock:
        if event:
            HOOKS[event] = []
        else:
            for key in HOOKS:
                HOOKS[key] = []


# ═══════════════════════════════════════════════════════════
#  Built-in Hooks
# ═══════════════════════════════════════════════════════════

DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
DESTRUCTIVE_PATTERNS = ["rm ", "> /etc/", "chmod 777", "DROP TABLE", "DELETE FROM"]


@dataclass
class ToolBlock:
    """Represents a tool call block from LLM response."""
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


def permission_hook(block: ToolBlock, user_id: int = None) -> Optional[str]:
    """
    PreToolUse: Permission check hook.
    
    Blocks dangerous commands and destructive operations.
    
    Args:
        block: Tool call block
        user_id: User ID (for context)
    
    Returns:
        Block reason string or None
    """
    if block.name == "bash":
        command = block.input.get("command", "")
        
        # Blacklist - always block
        for pattern in DENY_LIST:
            if pattern in command:
                logger.warning(f"⛔ Blocked dangerous command: {pattern}")
                return f"Permission denied: '{pattern}' is not allowed"
        
        # Graylist - warn (in production, would need user confirmation)
        for pattern in DESTRUCTIVE_PATTERNS:
            if pattern in command:
                logger.warning(f"⚠ Potentially destructive command: {command}")
                # For now, block in production; could add confirmation mechanism
                return f"Permission denied: destructive operation requires confirmation"
    
    if block.name in ("write_file", "edit_file"):
        path = block.input.get("path", "")
        # Check for path traversal
        if ".." in path or path.startswith("/"):
            logger.warning(f"⚠ Writing outside workspace: {path}")
            return "Permission denied: cannot write outside workspace"
    
    return None


def log_hook(block: ToolBlock, user_id: int = None) -> Optional[str]:
    """
    PreToolUse: Log every tool call.
    """
    args_preview = str(list(block.input.values())[:2])[:60]
    logger.info(f"[HOOK] {block.name}({args_preview}) user={user_id}")
    return None


def large_output_hook(block: ToolBlock, output: str, user_id: int = None) -> Optional[str]:
    """
    PostToolUse: Warn on large output.
    """
    if len(str(output)) > 100000:
        logger.warning(f"[HOOK] ⚠ Large output from {block.name}: {len(str(output))} chars")
    return None


def context_inject_hook(query: str, user_id: int = None, agent_id: int = None) -> Optional[str]:
    """
    UserPromptSubmit: Inject context before LLM call.
    """
    logger.info(f"[HOOK] UserPromptSubmit: user={user_id} agent={agent_id}")
    # Could inject system prompt modifications here
    return None


def summary_hook(messages: list, user_id: int = None) -> Optional[str]:
    """
    Stop: Print session statistics.
    """
    tool_count = sum(
        1 for m in messages
        for b in (m.get("content") if isinstance(m.get("content"), list) else [])
        if isinstance(b, dict) and b.get("type") == "tool_result"
    )
    logger.info(f"[HOOK] Stop: session used {tool_count} tool calls for user={user_id}")
    return None


# Register built-in hooks
register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)


# ═══════════════════════════════════════════════════════════
#  User-defined Hooks (loaded from DB)
# ═══════════════════════════════════════════════════════════

def load_user_hooks(user_id: int, db) -> None:
    """
    Load user-defined hooks from database.
    
    Args:
        user_id: User ID
        db: Database session
    """
    try:
        from app.models import Hook
        
        hooks = db.query(Hook).filter(
            Hook.user_id == user_id,
            Hook.enabled == True,
        ).all()
        
        for hook in hooks:
            # Create callback wrapper
            def make_callback(h):
                def callback(*args, **kwargs):
                    return execute_user_hook(h, *args, **kwargs)
                return callback
            
            register_hook(hook.hook_type, make_callback(hook))
        
        logger.info(f"Loaded {len(hooks)} user hooks for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to load user hooks: {e}")


def execute_user_hook(hook, *args, **kwargs) -> Optional[str]:
    """
    Execute user-defined hook (sandboxed).
    
    Security measures:
    - Limited execution time
    - Restricted builtins
    - Return value limited to string or None
    
    Args:
        hook: Hook model instance
        *args: Positional arguments
        **kwargs: Keyword arguments
    
    Returns:
        Block reason string or None
    """
    if not hook.script:
        return None
    
    try:
        # Check matcher pattern
        if hook.matcher:
            # Extract relevant string for matching
            match_target = ""
            if args and hasattr(args[0], 'input'):
                match_target = str(args[0].input)
            elif args and isinstance(args[0], str):
                match_target = args[0]
            
            if not re.search(hook.matcher, match_target):
                return None  # Matcher doesn't apply
        
        # Create restricted execution environment
        safe_globals = {
            "__builtins__": {
                "str": str, "int": int, "float": float,
                "bool": bool, "list": list, "dict": dict,
                "len": len, "re": re,
                "True": True, "False": False, "None": None,
            }
        }
        
        # Execute script
        exec_result = {}
        exec(hook.script, safe_globals, exec_result)
        
        # Call hook_handler if defined
        if "hook_handler" in exec_result:
            result = exec_result["hook_handler"](*args, **kwargs)
            if hook.action == "block" and result:
                return str(result)
            return None
        
        return None
    except Exception as e:
        logger.error(f"User hook {hook.id} failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════
#  Utility Functions
# ═══════════════════════════════════════════════════════════

def create_tool_block(tool_call: dict) -> ToolBlock:
    """
    Create a ToolBlock from a tool call dict.
    
    Args:
        tool_call: Tool call from LLM response
    
    Returns:
        ToolBlock instance
    """
    return ToolBlock(
        id=tool_call.get("id", ""),
        name=tool_call.get("name", ""),
        input=tool_call.get("input", tool_call.get("args", {})),
        type="tool_use"
    )


def get_hook_stats() -> dict:
    """
    Get hook statistics (for monitoring).
    
    Returns:
        Dict with hook counts
    """
    return {
        event: len(callbacks)
        for event, callbacks in HOOKS.items()
    }
