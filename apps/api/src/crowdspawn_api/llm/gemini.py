from typing import Any

import httpx

from .base import LLMAuthError, LLMBadResponseError, LLMResult, Message, post_json

BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    """Gemini REST generateContent. Enforces JSON natively via responseJsonSchema."""

    name = "gemini"
    supports_native_schema = True

    def __init__(self, api_key: str, model: str, http: httpx.AsyncClient | None = None):
        if not api_key:
            raise LLMAuthError("GEMINI_API_KEY is empty")
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
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in messages
            if m["role"] != "system"
        ]
        config: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_schema:
            config |= {"responseMimeType": "application/json", "responseJsonSchema": json_schema}
        body: dict[str, Any] = {"contents": contents, "generationConfig": config}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        data = await post_json(
            self.http,
            f"{BASE}/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            body=body,
            timeout=timeout,
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as e:
            raise LLMBadResponseError("missing candidates[0].content.parts") from e
        meta = data.get("usageMetadata") or {}
        return LLMResult(
            text=text,
            model=self.model,
            provider=self.name,
            raw=data,
            usage={
                "prompt": meta.get("promptTokenCount", 0),
                "output": meta.get("candidatesTokenCount", 0),
            },
        )

    async def aclose(self) -> None:
        await self.http.aclose()
