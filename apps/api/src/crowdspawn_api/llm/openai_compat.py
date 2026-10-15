from typing import Any

import httpx

from .base import LLMAuthError, LLMBadResponseError, LLMResult, Message, post_json


class OpenAICompatProvider:
    """Any OpenAI-style /chat/completions endpoint, configured by base URL, key and model."""

    name = "openai_compat"
    supports_native_schema = False

    def __init__(
        self, base_url: str, api_key: str, model: str, http: httpx.AsyncClient | None = None
    ):
        if not api_key or not base_url:
            raise LLMAuthError("OPENAI_COMPAT_BASE_URL or OPENAI_COMPAT_API_KEY is empty")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http = http or httpx.AsyncClient()

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        json_schema: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> LLMResult:
        data = await post_json(
            self.http,
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            body={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMBadResponseError("missing choices[0].message.content") from e
        u = data.get("usage") or {}
        return LLMResult(
            text=text,
            model=self.model,
            provider=self.name,
            raw=data,
            usage={"prompt": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0)},
        )

    async def aclose(self) -> None:
        await self.http.aclose()
