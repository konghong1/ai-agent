from __future__ import annotations

import asyncio
from typing import AsyncIterator

from .base import LLMAdapter, LLMConfig


class OpenAICompatibleAdapter(LLMAdapter):
    """OpenAI 兼容格式的 LLM 适配器。

    覆盖范围: 所有支持 /v1/chat/completions 端点的厂商:
    - OpenAI 自身
    - 硅基流动 (SiliconFlow)
    - 阿里云 DashScope (兼容格式)
    - 火山引擎 (Volcengine)
    - 零一万物 (01.ai)
    - 以及其他任何 OpenAI 兼容端点
    """

    provider_type = "openai-compatible"

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        api_key: str = "",
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._extra = kwargs

    def _build_client(self):
        """懒加载 OpenAI 客户端"""
        from openai import AsyncOpenAI
        import httpx

        # Force a direct connection: the injected egress proxy is optional
        # infrastructure and may be unreachable; direct egress works in this
        # deployment (see app/http_client). This keeps chat resilient to a
        # dead proxy. Remove proxy=None only in a proxy-only deployment.
        return AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=httpx.AsyncClient(proxy=None),
        )

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
