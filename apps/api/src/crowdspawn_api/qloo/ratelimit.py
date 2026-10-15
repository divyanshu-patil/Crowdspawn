import asyncio
import time
from collections.abc import Awaitable, Callable


class TokenBucket:
    """Capacity-1 token bucket: calls are spaced at least 1/rate seconds apart.

    Capacity 1 means no bursts, so any 1-second window holds at most `rate` calls.
    Clock and sleep are injectable for tests.
    """

    def __init__(
        self,
        rate: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.interval = 1.0 / rate
        self.clock = clock
        self.sleep = sleep
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = self.clock()
            if now < self._next:
                await self.sleep(self._next - now)
                now = self._next
            self._next = now + self.interval
