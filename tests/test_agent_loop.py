"""
Tests for Model-Driven Agent Loop V2

Tests:
1. Hook system (registration, triggering, blocking)
2. Tool Pool caching (hit/miss, invalidation)
3. agent_loop (tool execution, stop conditions)
4. Integration with API (V2 architecture switch)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════
#  Hook System Tests
# ═══════════════════════════════════════════════════════════

class TestHooks:
    """Test hook system functionality."""
    
    def test_hook_registration(self):
        """Test that hooks can be registered."""
        from app.hooks import register_hook, clear_hooks, HOOKS
        
        # Clear first
        clear_hooks()
        
        # Register a test hook
        def test_hook(*args):
            return None
        
        register_hook("UserPromptSubmit", test_hook)
        
        assert test_hook in HOOKS["UserPromptSubmit"]
        
        # Clean up
        clear_hooks("UserPromptSubmit")
    
    def test_hook_trigger_no_block(self):
        """Test that hooks can be triggered without blocking."""
        from app.hooks import register_hook, trigger_hooks, clear_hooks
        
        clear_hooks()
        
        called = []
        
        def test_hook(*args):
            called.append(args)
            return None  # No block
        
        register_hook("PreToolUse", test_hook)
        
        result = trigger_hooks("PreToolUse", "test_arg")
        
        assert result is None  # No block
        assert len(called) == 1
        assert called[0][0] == "test_arg"
        
        clear_hooks("PreToolUse")
    
    def test_hook_trigger_with_block(self):
        """Test that hooks can block execution."""
        from app.hooks import register_hook, trigger_hooks, clear_hooks
        
        clear_hooks()
        
        def blocking_hook(*args):
            return "Blocked for testing"
        
        register_hook("PreToolUse", blocking_hook)
        
        result = trigger_hooks("PreToolUse", "test_arg")
        
        assert result == "Blocked for testing"
        
        clear_hooks("PreToolUse")
    
    def test_permission_hook_blocks_dangerous_command(self):
        """Test that permission_hook blocks dangerous commands."""
        from app.hooks import permission_hook
        from app.hooks import ToolBlock
        
        block = ToolBlock(
            id="test-1",
            name="bash",
            input={"command": "rm -rf /"},
        )
        
        result = permission_hook(block, user_id=1)
        
        assert result is not None
        assert "Permission denied" in result
    
    def test_permission_hook_allows_safe_command(self):
        """Test that permission_hook allows safe commands."""
        from app.hooks import permission_hook
        from app.hooks import ToolBlock
        
        block = ToolBlock(
            id="test-1",
            name="bash",
            input={"command": "ls -la"},
        )
        
        result = permission_hook(block, user_id=1)
        
        assert result is None


# ═══════════════════════════════════════════════════════════
#  Tool Pool Tests
# ═══════════════════════════════════════════════════════════

class TestToolPool:
    """Test tool pool caching."""
    
    def test_tool_pool_singleton(self):
        """Test that ToolPool is a singleton."""
        from app.tool_pool import ToolPool, get_tool_pool
        
        pool1 = get_tool_pool()
        pool2 = ToolPool()
        
        assert pool1 is pool2
    
    def test_tool_pool_invalidation(self):
        """Test that tool pool can be invalidated."""
        from app.tool_pool import ToolPool, invalidate_tool_pool
        
        # Set up fake cache
        ToolPool._cache[123] = Mock()
        
        # Invalidate specific user
        invalidate_tool_pool(user_id=123, reason="test")
        
        assert 123 not in ToolPool._cache
    
    def test_tool_pool_stats(self):
        """Test that tool pool stats are returned."""
        from app.tool_pool import ToolPool
        
        stats = ToolPool.get_stats()
        
        assert "cache_size" in stats
        assert "users" in stats


# ═══════════════════════════════════════════════════════════
#  Agent Loop Tests
# ═══════════════════════════════════════════════════════════

class TestAgentLoop:
    """Test agent_loop functionality."""
    
    def test_agent_loop_stops_when_no_tool_use(self):
        """Test that agent_loop stops when stop_reason != 'tool_use'."""
        from app.agent_loop import agent_loop
        
        # Mock LLM that returns non-tool response
        mock_response = Mock()
        mock_response.content = "Hello, how can I help?"
        mock_response.stop_reason = "end_turn"
        
        mock_llm = Mock()
        mock_llm.invoke = Mock(return_value=mock_response)
        
        messages = [{"role": "user", "content": "Hi"}]
        events = list(agent_loop(messages, tools=[], llm=mock_llm))
        
        # Should have at least one "done" event
        done_events = [e for e in events if e[0] == "done"]
        assert len(done_events) == 1
        assert done_events[0][1]["content"] == "Hello, how can I help?"
    
    def test_agent_loop_executes_tools(self):
        """Test that agent_loop executes tools when requested."""
        from app.agent_loop import agent_loop, TOOL_HANDLERS
        
        # Register a test tool handler
        TOOL_HANDLERS["test_tool"] = Mock(return_value="Tool result")
        
        # Mock LLM that requests tool use
        mock_response = Mock()
        mock_response.content = ""
        mock_response.stop_reason = "tool_use"
        
        # Create mock tool call
        mock_tool_call = {
            "id": "call-1",
            "name": "test_tool",
            "input": {"arg": "value"},
        }
        
        # Patch _extract_tool_calls to return our tool call
        with patch('app.agent_loop._extract_tool_calls') as mock_extract:
            mock_extract.return_value = [mock_tool_call]
            
            mock_llm = Mock()
            mock_llm.invoke = Mock(return_value=mock_response)
            
            messages = [{"role": "user", "content": "Test"}]
            events = list(agent_loop(messages, tools=[], llm=mock_llm, max_iterations=2))
            
            # Should have tool_use and tool_result events
            tool_events = [e for e in events if e[0] == "tool_use"]
            assert len(tool_events) >= 1
            # Check the tool name in the event data
            tool_event_data = tool_events[0][1]
            assert "test_tool" in str(tool_event_data) or tool_event_data.get("name") == "test_tool"
        
        # Clean up
        del TOOL_HANDLERS["test_tool"]
    
    def test_tool_handler_registration(self):
        """Test that tool handlers can be registered."""
        from app.agent_loop import register_tool_handler, TOOL_HANDLERS
        
        def test_handler(input: str) -> str:
            return f"Processed: {input}"
        
        register_tool_handler("test_handler", test_handler)
        
        assert "test_handler" in TOOL_HANDLERS
        assert TOOL_HANDLERS["test_handler"]("test") == "Processed: test"
        
        # Clean up
        del TOOL_HANDLERS["test_handler"]


# ═══════════════════════════════════════════════════════════
#  Integration Tests
# ═══════════════════════════════════════════════════════════

class TestIntegration:
    """Integration tests."""
    
    def test_v2_architecture_switch_off(self):
        """Test that V2 architecture is off by default."""
        from app.agent_v2 import should_use_v2_architecture
        
        # Should be False by default
        assert should_use_v2_architecture() == False
    
    def test_settings_v2_fields_exist(self):
        """Test that V2 settings fields exist."""
        from app.settings import get_settings
        
        settings = get_settings()
        
        assert hasattr(settings, "use_agent_v2")
        assert hasattr(settings, "enable_knowledge_tool")
        assert settings.use_agent_v2 == False
        assert settings.enable_knowledge_tool == True


# ═══════════════════════════════════════════════════════════
#  Run Tests
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
