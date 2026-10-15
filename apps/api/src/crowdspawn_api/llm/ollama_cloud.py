from typing import Any

import httpx

from .base import LLMAuthError, LLMBadResponseError, LLMResult, Message, post_json


class OllamaCloudProvider:
    """Ollama's hosted API (https://ollama.com/api/chat). Never a local Ollama."""

    name = "ollama_cloud"
    supports_native_schema = False  # structured outputs are not supported on Ollama cloud

    def __init__(
        self, base_url: str, api_key: str, model: str, http: httpx.AsyncClient | None = None
    ):
        if not api_key:
            raise LLMAuthError("OLLAMA_API_KEY is empty")
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
            f"{self.base_url}/api/chat",
            headers={"Authorization": f"Bearer {self.api_key}"},
            body={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=timeout,
        )
        text = (data.get("message") or {}).get("content")
        if not isinstance(text, str):
            raise LLMBadResponseError("missing message.content")
        return LLMResult(
            text=text,
            model=self.model,
            provider=self.name,
            raw=data,
            usage={"prompt": data.get("prompt_eval_count", 0), "output": data.get("eval_count", 0)},
        )

    async def aclose(self) -> None:
        await self.http.aclose()
