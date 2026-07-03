from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class LLMConfig:
    """LLM 适配器通用配置"""
    provider_type: str = "openai-compatible"
    model_name: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    extra_kwargs: dict = field(default_factory=dict)


class LLMAdapter(ABC):
    """所有 LLM 适配器的统一抽象基类。

    新增厂商只需:
    1. 继承 LLMAdapter
    2. 实现 chat() 和 chat_stream() 两个抽象方法
    3. 在 PROVIDER_MAP 中注册
    """

    provider_type: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
        **kwargs,
    ) -> str:
        """同步对话请求，返回完整回复文本。

        Args:
            messages: [{"role": "user", "content": "..."}, ...]
            config: LLM 配置 (可被实现忽略)
            **kwargs: 额外参数

        Returns:
            助手回复文本
        """
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式对话请求，yield 每个增量文本 token。

        Args:
            messages: 消息列表
            config: LLM 配置

        Yields:
            每个增量文本 (非完整回复)
        """
        ...
