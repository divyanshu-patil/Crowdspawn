"""Persistence (SQLite file or Postgres URL): plans, agent runs, their events (for SSE replay),
traces and the Qloo cache. The SQL is written once, in the dialect both engines accept."""

import asyncio
import json
import re
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import asyncpg

# DOUBLE PRECISION, not REAL: Postgres REAL is 4 bytes and would round epoch seconds to minutes.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, input TEXT NOT NULL,
  result TEXT, error TEXT, created_at DOUBLE PRECISION NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, status TEXT NOT NULL, input TEXT NOT NULL,
  result TEXT, created_at DOUBLE PRECISION NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS events (
  plan_id TEXT NOT NULL, seq INTEGER NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL,
  PRIMARY KEY (plan_id, seq)
)""",
    """CREATE TABLE IF NOT EXISTS traces (
  plan_id TEXT NOT NULL, seq INTEGER NOT NULL, entry TEXT NOT NULL,
  PRIMARY KEY (plan_id, seq)
)""",
    """CREATE TABLE IF NOT EXISTS cache (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL
)""",
    "CREATE TABLE IF NOT EXISTS qloo_daily (day TEXT PRIMARY KEY, calls INTEGER NOT NULL)",
]

Row = Sequence[Any] | asyncpg.Record


def utc_day() -> str:
    return datetime.now(UTC).date().isoformat()


def pg_params(sql: str) -> str:
    """`?` placeholders to Postgres `$1, $2, …` (none of our SQL has a literal `?`)."""
    n = iter(range(1, 1000))
    return re.sub(r"\?", lambda _: f"${next(n)}", sql)


class _Sqlite:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def fetchone(self, sql: str, args: Sequence[Any] = ()) -> Row | None:
        async with self.db.execute(sql, args) as c:
            row = await c.fetchone()
        await self.db.commit()  # RETURNING writes need it; a no-op after reads
        return row

    async def fetchall(self, sql: str, args: Sequence[Any] = ()) -> list[Row]:
        async with self.db.execute(sql, args) as c:
            return list(await c.fetchall())

    async def execute(self, sql: str, args: Sequence[Any] = ()) -> None:
        await self.db.execute(sql, args)
        await self.db.commit()

    async def executemany(self, sql: str, rows: list[Sequence[Any]]) -> None:
        await self.db.executemany(sql, rows)
        await self.db.commit()

    async def close(self) -> None:
        await self.db.close()


class _Postgres:  # autocommit per statement, like the SQLite side
    def __init__(self, pool: "asyncpg.Pool[asyncpg.Record]"):
        self.pool = pool

    async def fetchone(self, sql: str, args: Sequence[Any] = ()) -> Row | None:
        return await self.pool.fetchrow(pg_params(sql), *args)

    async def fetchall(self, sql: str, args: Sequence[Any] = ()) -> list[Row]:
        return list(await self.pool.fetch(pg_params(sql), *args))

    async def execute(self, sql: str, args: Sequence[Any] = ()) -> None:
        await self.pool.execute(pg_params(sql), *args)

    async def executemany(self, sql: str, rows: list[Sequence[Any]]) -> None:
        await self.pool.executemany(pg_params(sql), rows)

    async def close(self) -> None:
        await self.pool.close()


class Store:
    def __init__(self, db: _Sqlite | _Postgres):
        self.db = db
        # seq = MAX+1 must not race between parallel steps.
        # ponytail: per-process lock, fine for one API instance; use a sequence if it scales out.
        self._event_lock = asyncio.Lock()

    @classmethod
    async def open(cls, target: Path | str) -> "Store":
        """`target` is a SQLite path (or ":memory:") or a postgres:// URL."""
        db: _Sqlite | _Postgres
        if str(target).startswith(("postgres://", "postgresql://")):
            # statement_cache_size=0: Supabase's transaction pooler (port 6543) can't keep
            # prepared statements across transactions.
            pool = await asyncpg.create_pool(
                str(target), min_size=1, max_size=5, statement_cache_size=0
            )
            db = _Postgres(pool)
        else:
            if str(target) != ":memory:":
                Path(target).parent.mkdir(parents=True, exist_ok=True)
            db = _Sqlite(await aiosqlite.connect(target))
        for stmt in SCHEMA:
            await db.execute(stmt)
        return cls(db)

    async def close(self) -> None:
        await self.db.close()

    # cache
    async def cache_get(self, key: str) -> Any | None:
        row = await self.db.fetchone("SELECT value, expires_at FROM cache WHERE key=?", (key,))
        if not row or row[1] < time.time():
            return None
        return json.loads(row[0])

    async def cache_put(self, key: str, value: Any, ttl: float) -> None:
        await self.db.execute(
            "INSERT INTO cache VALUES (?,?,?) ON CONFLICT(key) DO UPDATE "
            "SET value=excluded.value, expires_at=excluded.expires_at",
            (key, json.dumps(value), time.time() + ttl),
        )

    # global daily Qloo budget, keyed by UTC date
    async def take_daily_call(self, cap: int) -> bool:
        """Count one live Qloo call for today; False (and no count) once `cap` calls are used."""
        row = await self.db.fetchone(
            "INSERT INTO qloo_daily VALUES (?, 1) ON CONFLICT(day) DO UPDATE "
            "SET calls = qloo_daily.calls + 1 WHERE qloo_daily.calls < ? RETURNING calls",
            (utc_day(), cap),
        )
        return row is not None

    async def daily_calls(self) -> int:
        row = await self.db.fetchone("SELECT calls FROM qloo_daily WHERE day=?", (utc_day(),))
        return int(row[0]) if row else 0

    # plans
    async def create_plan(self, plan_id: str, input_: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO plans VALUES (?,?,?,?,?,?)",
            (plan_id, "queued", json.dumps(input_), None, None, time.time()),
        )

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

    async def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchone(
            "SELECT id, status, input, result, error, created_at FROM plans WHERE id=?", (plan_id,)
        )
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

    async def finish_run(self, run_id: str, status: str, result: dict[str, Any]) -> None:
        await self.db.execute(
            "UPDATE runs SET status=?, result=? WHERE id=?", (status, json.dumps(result), run_id)
        )

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = await self.db.fetchone(
            "SELECT id, status, input, result, created_at FROM runs WHERE id=?", (run_id,)
        )
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
            row = await self.db.fetchone(
                "SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE plan_id=?", (plan_id,)
            )
            seq = int(row[0]) if row else 1
            await self.db.execute(
                "INSERT INTO events VALUES (?,?,?,?)", (plan_id, seq, type_, json.dumps(data))
            )
            return seq

    async def events_after(self, plan_id: str, seq: int) -> list[tuple[int, str, dict[str, Any]]]:
        rows = await self.db.fetchall(
            "SELECT seq, type, data FROM events WHERE plan_id=? AND seq>? ORDER BY seq",
            (plan_id, seq),
        )
        return [(r[0], r[1], json.loads(r[2])) for r in rows]

    # traces
    async def save_trace(self, plan_id: str, entries: list[dict[str, Any]]) -> None:
        await self.db.executemany(
            "INSERT INTO traces VALUES (?,?,?) ON CONFLICT(plan_id, seq) DO UPDATE "
            "SET entry=excluded.entry",
            [(plan_id, i, json.dumps(e)) for i, e in enumerate(entries)],
        )

    async def get_trace(self, plan_id: str) -> list[dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT entry FROM traces WHERE plan_id=? ORDER BY seq", (plan_id,)
        )
        return [json.loads(r[0]) for r in rows]
