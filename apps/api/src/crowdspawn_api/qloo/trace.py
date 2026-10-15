from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class TraceEntry:
    result_id: str
    step: str
    endpoint: str
    params: dict[str, str]
    cache_hit: bool
    status: int
    duration_ms: int
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


OnCall = Callable[[TraceEntry], Awaitable[None]]


class Trace:
    """Ordered record of every Qloo call in one run. Never holds the API key."""

    def __init__(self, on_call: OnCall | None = None):
        self.entries: list[TraceEntry] = []
        self.on_call = on_call

    def next_id(self) -> str:
        return f"q{len(self.entries) + 1}"

    async def add(self, entry: TraceEntry) -> None:
        self.entries.append(entry)
        if self.on_call:
            await self.on_call(entry)

    def ids(self) -> set[str]:
        return {e.result_id for e in self.entries}

    def dump(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in sorted(self.entries, key=lambda e: int(e.result_id[1:]))]
