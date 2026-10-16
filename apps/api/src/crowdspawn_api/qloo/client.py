"""Async Qloo client: rate limit, retries, sqlite cache, per-run budget and call trace."""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from ..errors import (
    QlooAuthError,
    QlooBudgetExceeded,
    QlooError,
    QlooRateLimited,
    QlooUnconfigured,
)
from ..settings import Settings
from ..storage import Store
from .ratelimit import TokenBucket
from .trace import OnCall, Trace, TraceEntry

log = logging.getLogger(__name__)
RETRY_STATUSES = {429, 500, 502, 503, 504}
ATTEMPTS = 3


def cache_key(path: str, params: dict[str, str]) -> str:
    raw = json.dumps([path, sorted(params.items())])
    return hashlib.sha256(raw.encode()).hexdigest()


class QlooClient:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        *,
        http: httpx.AsyncClient | None = None,
        bucket: TokenBucket | None = None,
        backoff: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.settings = settings
        self.store = store
        self.bucket = bucket or TokenBucket(settings.qloo_rps)
        self.backoff = backoff
        self.http = http or httpx.AsyncClient(
            base_url=settings.qloo_base_url, timeout=settings.qloo_timeout_seconds
        )
        self.live_calls = 0

    @property
    def configured(self) -> bool:
        return bool(self.settings.qloo_api_key.get_secret_value().strip())

    def run(self, on_call: OnCall | None = None, max_calls: int | None = None) -> "QlooRun":
        return QlooRun(self, Trace(on_call), max_calls or self.settings.qloo_max_calls_per_run)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _fetch(self, path: str, params: dict[str, str]) -> tuple[int, Any]:
        key = self.settings.qloo_api_key.get_secret_value().strip()
        if not key:
            raise QlooUnconfigured("Set QLOO_API_KEY in apps/api/.env")
        last = "no response"
        for attempt in range(ATTEMPTS):
            await self.bucket.acquire()
            self.live_calls += 1
            try:
                r = await self.http.get(path, params=params, headers={"X-Api-Key": key})
            except httpx.TimeoutException:
                last = "timeout"
            except httpx.HTTPError as e:
                last = type(e).__name__
            else:
                if r.status_code in (401, 403):
                    raise QlooAuthError(f"Qloo returned {r.status_code}")
                if r.status_code not in RETRY_STATUSES:
                    try:
                        return r.status_code, r.json()
                    except ValueError as e:
                        raise QlooError("Qloo returned a non-JSON body") from e
                last = f"HTTP {r.status_code}"
                if r.status_code == 429 and attempt == ATTEMPTS - 1:
                    raise QlooRateLimited("Qloo kept returning 429")
            await self.backoff(0.5 * 2**attempt)
        raise QlooError(f"Qloo unavailable after {ATTEMPTS} attempts ({last})")


class QlooRun:
    """One plan's (or one request's) view of the client: shared budget and trace."""

    def __init__(self, client: QlooClient, trace: Trace, max_calls: int):
        self.client = client
        self.trace = trace
        self.max_calls = max_calls
        self.calls = 0

    async def get(
        self, step: str, path: str, params: dict[str, str], ttl: float | None = None
    ) -> tuple[str, Any]:
        if self.calls >= self.max_calls:
            raise QlooBudgetExceeded(f"More than {self.max_calls} Qloo calls in one run")
        self.calls += 1
        # Assign the id before awaiting so ids are deterministic under asyncio.gather.
        result_id = f"q{self.calls}"
        key = cache_key(path, params)
        start = time.perf_counter()
        status, cache_hit, body = 200, True, await self.client.store.cache_get(key)
        try:
            if body is None:
                cache_hit = False
                status, body = await self.client._fetch(path, params)
                if status == 200:
                    await self.client.store.cache_put(
                        key, body, ttl or self.client.settings.qloo_cache_ttl_seconds
                    )
        except QlooError as e:
            status = getattr(e, "status", 502)
            raise
        finally:
            await self.trace.add(
                TraceEntry(
                    result_id=result_id,
                    step=step,
                    endpoint=path,
                    params=dict(params),
                    cache_hit=cache_hit,
                    status=status,
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )
            )
        if status != 200:
            msg = (
                "; ".join(e.get("message", "") for e in body.get("errors", []))
                if isinstance(body, dict)
                else ""
            )
            raise QlooError(
                f"Qloo {path} returned {status}: {msg or 'error'}", code="qloo_bad_request"
            )
        return result_id, body
