"""Export a finished plan's Qloo responses (from the sqlite cache) as test fixtures,
and the plan + trace as the web app's /sample data. No live calls.

Usage: uv run python scripts/export_plan_fixtures.py <plan_id> <fixture_dir_name> [--sample]
"""

import asyncio
import json
import sys
from pathlib import Path

from crowdspawn_api.qloo.client import cache_key
from crowdspawn_api.settings import get_settings
from crowdspawn_api.storage import Store

ROOT = Path(__file__).resolve().parents[1]
WEB_PUBLIC = ROOT.parents[1] / "apps" / "web" / "public"


KEEP_PROPS = {"image", "audience_tags", "emotional_tone", "genre", "release_year"}


def trim(body: dict) -> dict:
    """Keep heatmap fixtures small: drop per-cell fields the app does not read."""
    results = body.get("results") if isinstance(body, dict) else None
    for c in results.get("heatmap", []) if isinstance(results, dict) else []:
        c["location"] = {k: round(c["location"][k], 4) for k in ("latitude", "longitude")}
        c["query"] = {k: round(c["query"][k], 4) for k in ("affinity", "affinity_rank")}
    entities = results.get("entities", []) if isinstance(results, dict) else results or []
    for e in entities:
        e["properties"] = {k: v for k, v in e.get("properties", {}).items() if k in KEEP_PROPS}
        e["tags"] = [{"name": t["name"]} for t in e.get("tags", []) if t.get("name")][:6]
        e.pop("external", None)
    return body


async def main(plan_id: str, name: str, sample: bool) -> None:
    store = await Store.open(get_settings().db_target)
    try:
        await export(store, plan_id, name, sample)
    finally:
        await store.close()


async def export(store: Store, plan_id: str, name: str, sample: bool) -> None:
    plan = await store.get_plan(plan_id)
    trace = await store.get_trace(plan_id)
    assert plan and plan["status"] == "done", "plan must be done"
    out = ROOT / "tests" / "fixtures" / "qloo" / name
    out.mkdir(parents=True, exist_ok=True)
    seen = set()
    for e in trace:
        key = cache_key(e["endpoint"], e["params"])
        if key in seen:
            continue
        seen.add(key)
        body = await store.cache_get(key)
        assert body is not None, f"{e['result_id']} not in cache"
        (out / f"{e['result_id']}.json").write_text(
            json.dumps(
                {
                    "request": {"path": e["endpoint"], "params": e["params"]},
                    "status": 200,
                    "body": trim(body),
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
    (out / "_plan_input.json").write_text(json.dumps(plan["input"], indent=2))
    if sample:
        result = plan["result"] | {"id": "sample"}
        (WEB_PUBLIC / "sample-plan.json").write_text(json.dumps(result, indent=1))
        (WEB_PUBLIC / "sample-trace.json").write_text(json.dumps(trace, indent=1))
    print(
        f"wrote {len(seen)} fixtures to {out.relative_to(ROOT)}" + (" + sample" if sample else "")
    )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], "--sample" in sys.argv))
