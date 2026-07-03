from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Type

from .base import LLMAdapter
from .openai_compat import OpenAICompatibleAdapter

if TYPE_CHECKING:
    pass


@dataclass
class LLMConfig:
    """LLM adapter generic configuration."""
    provider_type: str = "openai-compatible"
    model_name: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    extra_kwargs: dict = field(default_factory=dict)

# All registered LLM adapters
PROVIDER_MAP: dict[str, Type[LLMAdapter]] = {
    "openai-compatible": OpenAICompatibleAdapter,
}

# Lazy-loaded adapters storage
_LOADED_ADAPTERS: dict[str, Type[LLMAdapter]] = {}


def _ensure_qwen_loaded() -> None:
    """Lazy-load QwenAdapter on first use."""
    if "qwen" in PROVIDER_MAP:
        return
    try:
        from .qwen import QwenAdapter
        PROVIDER_MAP["qwen"] = QwenAdapter
    except ImportError:
        pass  # dashscope not installed


def _load_adapter(provider_type: str) -> Type[LLMAdapter] | None:
    """Load adapter by type, lazily registering Qwen if needed."""
    if provider_type in PROVIDER_MAP:
        return PROVIDER_MAP[provider_type]
    if provider_type in _LOADED_ADAPTERS:
        return _LOADED_ADAPTERS[provider_type]
    # Ensure Qwen is registered
    if provider_type == "qwen":
        _ensure_qwen_loaded()
    return PROVIDER_MAP.get(provider_type) or _LOADED_ADAPTERS.get(provider_type)


def register_adapter(provider_type: str, adapter_cls: Type[LLMAdapter]) -> None:
    """Register a new LLM adapter dynamically.

    Third-party adapters can register via:
        register_adapter("custom", CustomAdapter)
    """
    PROVIDER_MAP[provider_type] = adapter_cls


class LLMFactory:
    """Factory for creating LLM adapters based on provider type."""

    @staticmethod
    def create(config: LLMConfig, **kwargs) -> LLMAdapter:
        """Create an LLMAdapter instance from config.

        Args:
            config: LLM configuration
            **kwargs: Extra parameters passed to adapter

        Returns:
            LLMAdapter instance

        Raises:
            ValueError: Unknown provider_type with no fallback
        """
        adapter_cls = _load_adapter(config.provider_type)
        if adapter_cls is None:
            # Fallback: try as OpenAI-compatible if base_url is set
            if config.base_url or config.provider_type.startswith("openai"):
                adapter_cls = OpenAICompatibleAdapter
            else:
                raise ValueError(
                    f"Unknown provider type: '{config.provider_type}'. "
                    f"Available: {list(PROVIDER_MAP.keys())}. "
                    "Or use 'openai-compatible' for any OpenAI-format endpoint."
                )

        return adapter_cls(
            model_name=config.model_name,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            **kwargs,
            **config.extra_kwargs,
        )

    @staticmethod
    def list_available_types() -> list[str]:
        """List all registered provider_type values."""
        _ensure_qwen_loaded()
        return sorted(set(list(PROVIDER_MAP.keys()) + list(_LOADED_ADAPTERS.keys())))


__all__ = ["LLMFactory", "LLMConfig", "LLMAdapter", "register_adapter", "PROVIDER_MAP", "_load_adapter"]
