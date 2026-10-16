"""SQLite persistence: plans, agent runs, their events (for SSE replay), traces and the Qloo cache."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, input TEXT NOT NULL,
  result TEXT, error TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, input TEXT NOT NULL,
  result TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  plan_id TEXT NOT NULL, seq INTEGER NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL,
  PRIMARY KEY (plan_id, seq)
);
CREATE TABLE IF NOT EXISTS traces (
  plan_id TEXT NOT NULL, seq INTEGER NOT NULL, entry TEXT NOT NULL,
  PRIMARY KEY (plan_id, seq)
);
CREATE TABLE IF NOT EXISTS cache (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL
);
"""


class Store:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db
        self._event_lock = asyncio.Lock()  # seq = MAX+1 must not race between parallel steps

    @classmethod
    async def open(cls, path: Path | str) -> "Store":
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(path)
        await db.executescript(SCHEMA)
        await db.commit()
        return cls(db)

    async def close(self) -> None:
        await self.db.close()

    # cache
    async def cache_get(self, key: str) -> Any | None:
        async with self.db.execute("SELECT value, expires_at FROM cache WHERE key=?", (key,)) as c:
            row = await c.fetchone()
        if not row or row[1] < time.time():
            return None
        return json.loads(row[0])

    async def cache_put(self, key: str, value: Any, ttl: float) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
            (key, json.dumps(value), time.time() + ttl),
        )
        await self.db.commit()

    # plans
    async def create_plan(self, plan_id: str, input_: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO plans VALUES (?,?,?,?,?,?)",
            (plan_id, "queued", json.dumps(input_), None, None, time.time()),
        )
        await self.db.commit()

    async def set_status(
        self,
        plan_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        await self.db.execute(
            "UPDATE plans SET status=?, result=?, error=? WHERE id=?",
            (
                status,
                json.dumps(result) if result else None,
                json.dumps(error) if error else None,
                plan_id,
            ),
        )
        await self.db.commit()

    async def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT id, status, input, result, error, created_at FROM plans WHERE id=?", (plan_id,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "status": row[1],
            "input": json.loads(row[2]),
            "result": json.loads(row[3]) if row[3] else None,
            "error": json.loads(row[4]) if row[4] else None,
            "created_at": row[5],
        }

    # agent runs (their events share the events table; ids never collide with plan ids)
    async def create_run(self, run_id: str, input_: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?)",
            (run_id, "running", json.dumps(input_), None, time.time()),
        )
        await self.db.commit()

    async def finish_run(self, run_id: str, status: str, result: dict[str, Any]) -> None:
        await self.db.execute(
            "UPDATE runs SET status=?, result=? WHERE id=?", (status, json.dumps(result), run_id)
        )
        await self.db.commit()

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT id, status, input, result, created_at FROM runs WHERE id=?", (run_id,)
        ) as c:
            row = await c.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "status": row[1],
            "input": json.loads(row[2]),
            "result": json.loads(row[3]) if row[3] else None,
            "created_at": row[4],
        }

    # events
    async def add_event(self, plan_id: str, type_: str, data: dict[str, Any]) -> int:
        async with self._event_lock:
            async with self.db.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE plan_id=?", (plan_id,)
            ) as c:
                row = await c.fetchone()
            seq = int(row[0]) if row else 1
            await self.db.execute(
                "INSERT INTO events VALUES (?,?,?,?)", (plan_id, seq, type_, json.dumps(data))
            )
            await self.db.commit()
            return seq

    async def events_after(self, plan_id: str, seq: int) -> list[tuple[int, str, dict[str, Any]]]:
        async with self.db.execute(
            "SELECT seq, type, data FROM events WHERE plan_id=? AND seq>? ORDER BY seq",
            (plan_id, seq),
        ) as c:
            rows = await c.fetchall()
        return [(r[0], r[1], json.loads(r[2])) for r in rows]

    # traces
    async def save_trace(self, plan_id: str, entries: list[dict[str, Any]]) -> None:
        await self.db.executemany(
            "INSERT OR REPLACE INTO traces VALUES (?,?,?)",
            [(plan_id, i, json.dumps(e)) for i, e in enumerate(entries)],
        )
        await self.db.commit()

    async def get_trace(self, plan_id: str) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT entry FROM traces WHERE plan_id=? ORDER BY seq", (plan_id,)
        ) as c:
            rows = await c.fetchall()
        return [json.loads(r[0]) for r in rows]
