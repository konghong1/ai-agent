"""Test token_counter module."""

import pytest
from app.token_counter import TokenCounter, TokenUsage


def test_token_counter_basic():
    """Test basic token counting."""
    counter = TokenCounter("gpt-4")

    # Test simple text
    text = "Hello, world!"
    count = counter.count_text(text)
    assert count > 0
    assert isinstance(count, int)

    # Test empty text
    assert counter.count_text("") == 0

    # Test messages
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    msg_count = counter.count_messages(messages)
    assert msg_count > 0
    assert isinstance(msg_count, int)


def test_token_usage_dataclass():
    """Test TokenUsage dataclass."""
    usage = TokenUsage(
        system_prompt=100,
        tools=200,
        messages=300,
        mcp=50,
        skills=30,
        total=680,
        max_tokens=4096,
    )

    result = usage.to_dict()
    assert result["system_prompt"] == 100
    assert result["tools"] == 200
    assert result["messages"] == 300
    assert result["total"] == 680
    assert result["max_tokens"] == 4096
    assert "usage_ratio" in result
    assert abs(result["usage_ratio"] - 0.166) < 0.001  # 680/4096 ≈ 0.166


def test_compute_usage():
    """Test compute_usage method."""
    counter = TokenCounter("gpt-4")

    system_prompt = "You are a helpful AI assistant."
    messages = [
        {"role": "user", "content": "What is the weather?"},
        {"role": "assistant", "content": "I don't have access to real-time weather data."},
    ]

    usage = counter.compute_usage(
        system_prompt=system_prompt,
        tools=[],
        messages=messages,
        max_tokens=8192,
    )

    assert usage.system_prompt > 0
    assert usage.messages > 0
    assert usage.total == usage.system_prompt + usage.messages
    assert usage.max_tokens == 8192
    assert usage.usage_ratio >= 0


def test_model_max_tokens():
    """Test get_max_tokens for different models."""
    counter = TokenCounter("gpt-4")

    # Test known models
    assert counter.get_max_tokens("gpt-4") == 8192
    assert counter.get_max_tokens("gpt-4-turbo") == 128000
    assert counter.get_max_tokens("gpt-3.5-turbo") == 16385

    # Test unknown model (should return default)
    assert counter.get_max_tokens("unknown-model") == 128000


def test_fallback_estimator():
    """Test fallback estimator when tiktoken is not available."""
    counter = TokenCounter("unknown-model")
    counter.encoding = None  # Force fallback

    text = "This is a test message with several words."
    count = counter.count_text(text)

    # Fallback: ~4 chars per token
    expected = len(text) // 4
    assert count == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
