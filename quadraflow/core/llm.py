"""
LLM抽象化レイヤー
OpenAI互換APIを使ってOllama/Groq/OpenAI/Anthropic/OpenRouter全てに対応
"""

import asyncio
import logging
from typing import AsyncIterator, Optional
from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from quadraflow.config import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI互換APIクライアント（全プロバイダー対応）"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = self._build_client(config)

    def _build_client(self, config: LLMConfig) -> AsyncOpenAI:
        """プロバイダーに応じたクライアントを構築"""
        api_key = config.api_key

        # Ollamaはapi_keyが不要だがライブラリが要求するので適当な値を設定
        if config.provider == "ollama" and not api_key:
            api_key = "ollama"

        return AsyncOpenAI(
            api_key=api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """非ストリーミング補完"""
        model = model or self.config.model
        temperature = temperature if temperature is not None else self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        logger.debug(f"LLM呼び出し: provider={self.config.provider}, model={model}")

        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """ストリーミング補完"""
        model = model or self.config.model
        temperature = temperature if temperature is not None else self.config.temperature
        max_tokens = max_tokens or self.config.max_tokens

        async with await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        ) as response:
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

    async def health_check(self) -> bool:
        """LLM接続確認"""
        try:
            await self.complete(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=10,
            )
            return True
        except Exception as e:
            logger.warning(f"LLMヘルスチェック失敗: {e}")
            return False
