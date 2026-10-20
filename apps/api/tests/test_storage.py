"""Store round trip on SQLite, and on Postgres when DATABASE_URL is set (`pnpm --filter api test:live`)."""

import os
import uuid
from pathlib import Path

import pytest

from crowdspawn_api.settings import get_settings
from crowdspawn_api.storage import Store, pg_params, utc_day


def test_pg_params() -> None:
    assert pg_params("a=? AND b>?") == "a=$1 AND b>$2"


async def roundtrip(store: Store) -> None:
    pid = f"test-{uuid.uuid4()}"
    await store.create_plan(pid, {"game": "Hades"})
    await store.set_status(pid, "done", result={"ok": 1})
    plan = await store.get_plan(pid)
    assert plan and plan["status"] == "done" and plan["result"] == {"ok": 1}
    assert plan["created_at"] > 1e9  # full epoch seconds, not a rounded float4
    assert [await store.add_event(pid, "step", {"i": i}) for i in range(2)] == [1, 2]
    assert await store.events_after(pid, 1) == [(2, "step", {"i": 1})]
    await store.save_trace(pid, [{"a": 1}])
    await store.save_trace(pid, [{"a": 2}])  # upsert, not a duplicate-key error
    assert await store.get_trace(pid) == [{"a": 2}]
    await store.cache_put(pid, [1], 60)
    await store.cache_put(pid, [2], 60)
    assert await store.cache_get(pid) == [2]
    await store.create_run(pid, {})
    await store.finish_run(pid, "done", {"r": 1})
    run = await store.get_run(pid)
    assert run and run["result"] == {"r": 1}
    before = await store.daily_calls()
    assert await store.take_daily_call(before + 1)
    assert not await store.take_daily_call(before + 1)
    # leave a shared (production) database as it was
    for table, col in [
        ("plans", "id"),
        ("runs", "id"),
        ("events", "plan_id"),
        ("traces", "plan_id"),
        ("cache", "key"),
    ]:
        await store.db.execute(f"DELETE FROM {table} WHERE {col}=?", (pid,))
    await store.db.execute("UPDATE qloo_daily SET calls = calls - 1 WHERE day=?", (utc_day(),))


async def test_sqlite_roundtrip(tmp_path: Path) -> None:
    store = await Store.open(tmp_path / "s.sqlite3")
    try:
        await roundtrip(store)
    finally:
        await store.close()


@pytest.mark.live
async def test_postgres_roundtrip() -> None:
    url = os.environ.get("DATABASE_URL") or get_settings().database_url.get_secret_value()
    if not url:
        pytest.skip("DATABASE_URL not set")
    store = await Store.open(url)
    try:
        await roundtrip(store)
    finally:
        await store.close()
