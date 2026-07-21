"""Token counting utilities for context management."""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token usage breakdown by category."""

    system_prompt: int = 0
    tools: int = 0
    messages: int = 0
    mcp: int = 0
    skills: int = 0
    total: int = 0
    max_tokens: int = 128000

    @property
    def usage_ratio(self) -> float:
        """Calculate usage ratio (total / max_tokens)."""
        if self.max_tokens <= 0:
            return 0.0
        return self.total / self.max_tokens

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "messages": self.messages,
            "mcp": self.mcp,
            "skills": self.skills,
            "total": self.total,
            "max_tokens": self.max_tokens,
            "usage_ratio": round(self.usage_ratio, 3),
        }


class TokenCounter:
    """Count tokens by category using tiktoken."""

    # Model max context mapping
    MODEL_MAX_TOKENS = {
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-turbo-preview": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-3.5-turbo": 16385,
        "gpt-3.5-turbo-16k": 16385,
        "claude-3-opus": 200000,
        "claude-3-sonnet": 200000,
        "claude-3-haiku": 200000,
        "claude-3-5-sonnet": 200000,
        # Default fallback
        "default": 128000,
    }

    def __init__(self, model_name: str = "gpt-4"):
        """Initialize tokenizer for given model."""
        self.model_name = model_name
        self.encoding = None

        # Try to load tiktoken
        try:
            import tiktoken
            # Map model names to tiktoken encodings
            if "gpt-4" in model_name or "gpt-3.5" in model_name:
                self.encoding = tiktoken.encoding_for_model(model_name)
            else:
                # Fallback to cl100k_base (GPT-4 encoding)
                self.encoding = tiktoken.get_encoding("cl100k_base")
            logger.info("TokenCounter initialized with tiktoken for model=%s", model_name)
        except ImportError:
            logger.warning("tiktoken not installed, using fallback estimator")
        except Exception as e:
            logger.warning("Failed to load tiktoken encoding: %s, using fallback", e)

    def count_text(self, text: str) -> int:
        """Count tokens in a text string."""
        if not text:
            return 0

        if self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception as e:
                logger.warning("tiktoken encode failed: %s, using fallback", e)

        # Fallback: ~4 chars per token (rough estimate)
        return len(text) // 4

    def count_messages(self, messages: list[dict]) -> int:
        """Count tokens in a message list (includes role overhead)."""
        if not messages:
            return 0

        total = 0
        for msg in messages:
            # Message overhead: ~4 tokens per message (role, separators, etc.)
            total += 4

            # Content
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count_text(content)
            elif isinstance(content, list):
                # Multimodal content (text + images)
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self.count_text(part["text"])
                    # Image tokens are estimated differently, skip for now

            # Tool calls
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    total += self.count_text(str(tc))

            # Name field
            if "name" in msg:
                total += self.count_text(msg["name"])

        return total

    def count_tools(self, tools: list[Any]) -> int:
        """Count tokens in tool definitions."""
        if not tools:
            return 0

        total = 0
        for tool in tools:
            # Tool name + description
            name = getattr(tool, "name", "")
            desc = getattr(tool, "description", "")
            total += self.count_text(name) + self.count_text(desc)

            # Args schema
            if hasattr(tool, "args_schema") and tool.args_schema:
                try:
                    schema = tool.args_schema.schema()
                    total += self.count_text(str(schema))
                except Exception:
                    pass

            # Approximate overhead per tool
            total += 10

        return total

    def get_max_tokens(self, model_name: str = None) -> int:
        """Get max context length for model."""
        name = model_name or self.model_name

        # Check exact match
        if name in self.MODEL_MAX_TOKENS:
            return self.MODEL_MAX_TOKENS[name]

        # Check partial match
        name_lower = name.lower()
        for key, value in self.MODEL_MAX_TOKENS.items():
            if key in name_lower:
                return value

        return self.MODEL_MAX_TOKENS["default"]

    def compute_usage(
        self,
        system_prompt: str,
        tools: list[Any],
        messages: list[dict],
        mcp_config: str = "",
        skills: list[str] = None,
        max_tokens: int = None,
    ) -> TokenUsage:
        """Compute token usage breakdown."""
        usage = TokenUsage(
            system_prompt=self.count_text(system_prompt or ""),
            tools=self.count_tools(tools or []),
            messages=self.count_messages(messages or []),
            mcp=self.count_text(mcp_config or ""),
            skills=sum(self.count_text(s) for s in (skills or [])),
            max_tokens=max_tokens or self.get_max_tokens(),
        )

        usage.total = (
            usage.system_prompt
            + usage.tools
            + usage.messages
            + usage.mcp
            + usage.skills
        )

        return usage
