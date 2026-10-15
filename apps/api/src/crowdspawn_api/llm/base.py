from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict

import httpx

from ..errors import AppError


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str
    usage: dict[str, int] | None = None
    raw: dict[str, Any] | None = None  # debugging only; never logged with prompts


class LLMError(AppError):
    status = 502
    code = "llm_unavailable"
    title = "LLM request failed"


class LLMAuthError(LLMError):
    title = "LLM rejected the API key or is not configured"


class LLMRateLimitError(LLMError):
    title = "LLM rate limit hit"


class LLMTimeoutError(LLMError):
    title = "LLM request timed out"


class LLMBadResponseError(LLMError):
    title = "LLM returned an unusable response"


class LLMProvider(Protocol):
    name: str
    model: str
    supports_native_schema: bool

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        json_schema: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> LLMResult: ...

    async def aclose(self) -> None: ...


async def post_json(
    http: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Shared HTTP call for adapters: maps transport and status errors to LLM errors."""
    try:
        r = await http.post(url, headers=headers, json=body, timeout=timeout)
    except httpx.TimeoutException as e:
        raise LLMTimeoutError() from e
    except httpx.HTTPError as e:
        raise LLMError(type(e).__name__) from e
    if r.status_code in (401, 403):
        raise LLMAuthError(f"HTTP {r.status_code}")
    if r.status_code == 429:
        raise LLMRateLimitError()
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}")
    try:
        data: dict[str, Any] = r.json()
    except ValueError as e:
        raise LLMBadResponseError("non-JSON body") from e
    return data
