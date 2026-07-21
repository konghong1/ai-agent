"""
Model-Driven Agent Loop

Based on learn-claude-code s04_hooks design:
- Agency comes from model, not from code orchestration
- Loop stays clean, hooks handle extensions
- Model decides when to call tools, code just executes

Core loop:
1. LLM invoke (with tools)
2. Check stop_reason
   - "tool_use" → execute tool → continue
   - other → yield done → return
3. Hook integration:
   - UserPromptSubmit: before LLM call
   - PreToolUse: before tool execution (can block)
   - PostToolUse: after tool execution
   - Stop: when model decides to stop
"""

import logging
import time
from typing import Any, Generator

logger = logging.getLogger(__name__)

from app.hooks import trigger_hooks, create_tool_block


# ═══════════════════════════════════════════════════════════
#  TOOL_HANDLERS Registry
# ═══════════════════════════════════════════════════════════

TOOL_HANDLERS: dict[str, callable] = {}


def register_tool_handler(name: str, handler: callable) -> None:
    """Register a tool handler."""
    TOOL_HANDLERS[name] = handler
    logger.info(f"Registered tool handler: {name}")


# ═══════════════════════════════════════════════════════════
#  Agent Loop (Core)
# ═══════════════════════════════════════════════════════════

def agent_loop(
    messages: list[dict],
    tools: list,
    llm,
    user_id: int = None,
    agent_id: int = None,
    max_iterations: int = 20,
) -> Generator[tuple[str, Any], None, None]:
    """
    Model-driven agent loop.
    
    The model decides:
    - Whether to call a tool
    - Which tool to call
    - When to stop
    
    The code only:
    - Executes tool calls the model requests
    - Triggers hooks at extension points
    
    Args:
        messages: Conversation history
        tools: Available tools (StructuredTool list)
        llm: LLM instance with invoke() method
        user_id: User ID (for hooks)
        agent_id: Agent ID (for hooks)
        max_iterations: Maximum loop iterations (prevent infinite loop)
    
    Yields:
        (event_type, event_data) tuples:
        - ("status", str): Progress message
        - ("delta", str): Text chunk
        - ("tool_use", dict): Tool call info
        - ("tool_result", str): Tool execution result
        - ("warning", str): Warning message
        - ("done", dict): Final response
    """
    iterations = 0
    
    while iterations < max_iterations:
        iterations += 1
        logger.info(f"Agent loop iteration {iterations}/{max_iterations}")
        
        # ── Step 1: Invoke LLM with tools ──
        try:
            yield ("status", f"正在思考... (第 {iterations} 轮)")
            
            # Convert tools to OpenAI format if needed
            tool_schemas = None
            if tools:
                tool_schemas = [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.args_schema.schema() if hasattr(t, 'args_schema') and t.args_schema else {}
                        }
                    }
                    for t in tools
                ]
            
            # Invoke LLM
            response = llm.invoke(messages, tools=tool_schemas)
            
        except Exception as e:
            logger.error(f"LLM invoke failed: {e}")
            yield ("error", f"LLM 调用失败: {str(e)}")
            return
        
        # ── Step 2: Append response to messages ──
        messages.append({"role": "assistant", "content": response.content})
        
        # ── Step 3: Check stop_reason ──
        if response.stop_reason != "tool_use":
            # Model decided to stop
            force = trigger_hooks("Stop", messages, user_id)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            
            # Yield final response
            yield ("done", {
                "content": response.content,
                "iterations": iterations,
            })
            return
        
        # ── Step 4: Process tool calls ──
        tool_calls = _extract_tool_calls(response)
        if not tool_calls:
            logger.warning("stop_reason=tool_use but no tool_calls found")
            yield ("warning", "模型请求工具调用但未找到工具定义")
            continue
        
        results = []
        for tool_call in tool_calls:
            block = create_tool_block(tool_call)
            
            # ── PreToolUse Hook ──
            blocked = trigger_hooks("PreToolUse", block, user_id)
            if blocked:
                yield ("status", f"工具 {block.name} 被拦截: {blocked}")
                results.append({
                    "tool_call_id": block.id,
                    "role": "tool",
                    "content": str(blocked),
                })
                continue
            
            # ── Execute tool ──
            yield ("tool_use", {
                "name": block.name,
                "input": block.input,
            })
            
            handler = TOOL_HANDLERS.get(block.name)
            if handler:
                try:
                    start_time = time.time()
                    output = handler(**block.input)
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    logger.info(f"Tool {block.name} executed in {elapsed_ms}ms")
                except Exception as e:
                    output = f"工具执行失败: {str(e)}"
                    logger.error(f"Tool {block.name} failed: {e}")
            else:
                output = f"未知工具: {block.name}"
                logger.warning(f"Unknown tool: {block.name}")
            
            # ── PostToolUse Hook ──
            trigger_hooks("PostToolUse", block, output, user_id)
            
            yield ("tool_result", output)
            
            results.append({
                "tool_call_id": block.id,
                "role": "tool",
                "content": output,
            })
        
        # ── Step 5: Append tool results to messages ──
        messages.append({"role": "user", "content": results})
        
        # ── Step 6: Continue loop ──
        yield ("status", f"已执行 {len(results)} 个工具，继续思考...")
    
    # ── Max iterations reached ──
    logger.warning(f"Max iterations ({max_iterations}) reached")
    yield ("warning", f"达到最大循环次数 ({max_iterations})")
    yield ("done", {
        "content": "抱歉，我遇到了一些复杂情况，无法完成任务。",
        "iterations": iterations,
    })


def _extract_tool_calls(response) -> list[dict]:
    """
    Extract tool calls from LLM response.
    
    Args:
        response: LLM response object
    
    Returns:
        List of tool call dicts with id, name, input/args
    """
    tool_calls = []
    
    # OpenAI-style tool_calls
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tc in response.tool_calls:
            tool_calls.append({
                "id": tc.id if hasattr(tc, 'id') else "",
                "name": tc.function.name if hasattr(tc, 'function') else tc.name,
                "input": tc.function.arguments if hasattr(tc, 'function') else tc.input,
            })
    
    # Anthropic-style content blocks
    elif hasattr(response, 'content') and isinstance(response.content, list):
        for block in response.content:
            if hasattr(block, 'type') and block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
    
    return tool_calls


# ═══════════════════════════════════════════════════════════
#  Utility Functions
# ═══════════════════════════════════════════════════════════

def build_messages_from_history(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    reference_images: list[str] = None,
) -> list[dict]:
    """
    Build messages list for LLM from conversation history.
    
    Args:
        system_prompt: System prompt
        history: Previous messages (list of {role, content} dicts)
        user_message: Current user message
        reference_images: Optional list of image URLs
    
    Returns:
        Messages list ready for LLM
    """
    messages = []
    
    # System prompt
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    # History
    messages.extend(history)
    
    # Current user message
    if reference_images:
        # Multimodal message
        content = [{"type": "text", "text": user_message}]
        for img_url in reference_images[:8]:
            if img_url.startswith("data:") or img_url.startswith("http"):
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img_url}
                })
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": user_message})
    
    return messages
