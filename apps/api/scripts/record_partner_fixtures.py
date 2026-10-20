"""Re-record a plan fixture's S5 partner calls after a change to partners.fetch_kind (live Qloo calls).

Usage: uv run python scripts/record_partner_fixtures.py <fixture-dir-name>
Reads the old S5 calls for the signal and the top cities, runs partners() through the local cache,
writes the new calls as qp*.json and deletes the old S5 files. Prints the live call count.
"""

import asyncio
import json
import sys
from pathlib import Path

from export_plan_fixtures import trim

from crowdspawn_api.pipeline import cities, partners
from crowdspawn_api.qloo.client import QlooClient, cache_key
from crowdspawn_api.settings import get_settings
from crowdspawn_api.storage import Store

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "qloo"


async def main(name: str) -> None:
    out = FIXTURES / name
    old = {}
    for f in out.glob("q*.json"):
        d = json.loads(f.read_text())
        t = d["request"]["params"].get("filter.type", "")
        if t.split(":")[-1] in partners.ALL_TYPES:
            old[f] = d["request"]["params"]
    signal = next(iter(old.values()))["signal.interests.entities"].split(",")
    points = {p["signal.location"] for p in old.values() if "signal.location" in p}
    regions = cities.regions()
    top = [r for r in regions.values() if f"POINT({r.lon} {r.lat})" in points]
    assert len(top) == len(points), (points, top)
    store = await Store.open(get_settings().db_target)
    qloo = QlooClient(get_settings(), store)
    try:
        run = qloo.run()
        await partners.partners(run, signal, {}, top)  # type: ignore[arg-type]
        for i, e in enumerate(run.trace.entries, 1):
            body = await store.cache_get(cache_key(e.endpoint, e.params))
            (out / f"qp{i}.json").write_text(
                json.dumps(
                    {
                        "request": {"path": e.endpoint, "params": e.params},
                        "status": 200,
                        "body": trim(body),
                    },
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
        print(f"{len(run.trace.entries)} calls, {qloo.live_calls} live")
    finally:
        await qloo.aclose()
        await store.close()
    for f in old:
        f.unlink()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
