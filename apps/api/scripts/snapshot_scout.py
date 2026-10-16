"""Snapshot "what works here" for 50 popular places into the web app, so they scout instantly.

Runs the real /v1/scout/area pipeline (Qloo heatmaps and located game insights) for each place and
writes apps/web/lib/scout-snapshot.json. Live: about 19 Qloo calls per place on a cold cache.
Run: uv run python scripts/snapshot_scout.py
"""

import asyncio
import json
from datetime import date
from pathlib import Path

from crowdspawn_api.errors import QlooError
from crowdspawn_api.pipeline import cities, scout
from crowdspawn_api.qloo.client import QlooClient
from crowdspawn_api.settings import get_settings
from crowdspawn_api.storage import Store

OUT = Path(__file__).resolve().parents[2] / "web" / "lib" / "scout-snapshot.json"
EXTRA = [  # biggest gaming cities outside the plan's candidate list
    "los", "cai", "jnb", "ruh", "khi", "dac", "bkk", "sgn", "kul",
    "tpe", "hkg", "sha", "bog", "lim", "scl", "rom", "ams",
]  # fmt: skip


async def main() -> None:
    s = get_settings()
    store = await Store.open(s.db_file)
    qloo = QlooClient(s, store)
    points = scout.scout_points()
    ids = list(cities.regions()) + EXTRA
    areas, skipped = [], []
    try:
        for pid in ids:
            p = points[pid]
            try:
                a = await scout.scout_area(qloo.run(max_calls=30), p.lat, p.lon, 40)
            except QlooError as e:
                skipped.append(f"{p.name}: {e.detail}")
                continue
            body = a.model_dump(mode="json", exclude={"calls"})
            body["games"] = [
                {"name": g["name"], "image_url": g["image_url"]} for g in body["games"]
            ]
            areas.append({"id": pid, "name": p.name, "country": p.country, **body})
            print(f"{p.name}: top genre {a.genres[0].genre} x{a.genres[0].lift}")
    finally:
        await qloo.aclose()
        await store.close()
    OUT.write_text(
        json.dumps(
            {"generated": date.today().isoformat(), "source": "qloo", "areas": areas},
            separators=(",", ":"),
        )
        + "\n"
    )
    print(f"wrote {len(areas)} places; skipped {skipped}; live calls {qloo.live_calls}")


if __name__ == "__main__":
    asyncio.run(main())
