from __future__ import annotations

from typing import AsyncIterator

from .base import LLMAdapter, LLMConfig


class QwenAdapter(LLMAdapter):
    """通义千问 (Qwen) 适配器。

    支持两种模式:
    1. dashscope SDK (官方)
    2. OpenAI 兼容格式 (阿里云 DashScope 提供的 /v1/chat/completions 端点)
    """

    provider_type = "qwen"

    def __init__(
        self,
        model_name: str = "qwen-max",
        api_key: str = "",
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._extra = kwargs

    def _build_client(self):
        """懒加载 OpenAI 兼容客户端 (通义千问提供 OpenAI 兼容端点)"""
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def chat(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
        **kwargs,
    ) -> str:
        client = self._build_client()
        params = {
            "model": config.model_name if config else self.model_name,
            "messages": messages,
            "temperature": config.temperature if config else self.temperature,
            **self._extra,
        }
        if config and config.max_tokens:
            params["max_tokens"] = config.max_tokens
        if kwargs:
            params.update(kwargs)

        response = await client.chat.completions.create(**params)
        return response.choices[0].message.content or ""

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        config: LLMConfig | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        client = self._build_client()
        params = {
            "model": config.model_name if config else self.model_name,
            "messages": messages,
            "temperature": config.temperature if config else self.temperature,
            "stream": True,
            **self._extra,
        }
        if config and config.max_tokens:
            params["max_tokens"] = config.max_tokens
        if kwargs:
            params.update(kwargs)

        stream = await client.chat.completions.create(**params)
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
