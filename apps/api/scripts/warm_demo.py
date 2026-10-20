"""Warm a running API before judging, so every demo input answers from cache.

Calls the public endpoints (local or deployed): the scout activity map, the judge for the demo places,
full plans for the demo games and both samples, "Scout this city" for each sample's top 3, and the launch
agent's first example (the one the pitch uses). Costs Qloo and LLM calls once; repeats are cached.
Run: uv run python scripts/warm_demo.py [http://localhost:8000]
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
DEFAULTS = ["nyc", "lax", "chi", "yto", "mex", "sao", "lon", "par", "ber", "waw", "ist", "dxb", "del", "bom", "tyo", "sel", "jkt", "syd"]  # fmt: skip

JUDGE = [  # (lat, lon, title, description, platforms)
    (
        51.51,
        -0.13,
        "Moss Hollow",
        "A cozy farming and village life sim with hand-painted art, gentle crafting and friendships with villagers.",
        ["pc", "console", "mobile"],
    ),  # fmt: skip
    (
        37.57,
        126.98,
        "Lane Legends",
        "A competitive 5v5 MOBA with short 15 minute matches and anime heroes.",
        ["pc", "mobile"],
    ),  # fmt: skip
    (
        35.68,
        139.69,
        "Ember Crypt",
        "A fast roguelike dungeon crawler with hand-drawn bosses and deckbuilding.",
        ["pc", "console"],
    ),  # fmt: skip
]
PLANS: list[dict[str, Any]] = [
    {  # roguelike: Hades, Dead Cells, Slay the Spire
        "game": {
            "title": "Ember Crypt",
            "description": "Roguelike dungeon crawler",
            "tags": ["roguelike"],
        },
        "comp_entity_ids": [
            "BA00D00A-E4CD-48C0-A22E-CFC52039D618",
            "870FBF81-80F8-401A-9621-63DBF6AB6C07",
            "20BEE4A4-44C1-49CC-962D-CC0B4EE80102",
        ],  # fmt: skip
        "platforms": ["pc", "console"],
        "regions": DEFAULTS,
        "budget_usd": 5000,
    },
]


PUBLIC = Path(__file__).resolve().parents[2] / "web/public"
SAMPLES = [
    json.loads((PUBLIC / f).read_text()) for f in ("sample-plan.json", "sample-delhi-plan.json")
]
PLANS += [s["input"] for s in SAMPLES]
AGENT_GOAL = (  # EXAMPLES[0] in apps/web/components/LaunchAgent.tsx
    "A cozy farming and village life game for PC and Switch. Where should I launch first, and who should I partner with?"
)


def from_plan(s: dict[str, Any], city: dict[str, Any]) -> dict[str, Any]:
    """The judge body the scout sends when opened from a plan (RegionScout.tsx fromPlan)."""
    g = s["input"]["game"]
    comps = s["comps"]
    desc = (
        g["description"]
        if len(g["description"].strip()) >= 10
        else f"{g['title']}, a game like {', '.join(c['name'] for c in comps)}"
    )
    return {
        "lat": city["lat"],
        "lon": city["lon"],
        "title": g["title"],
        "description": desc[:600],
        "platforms": s["input"]["platforms"],
        "comp_entity_ids": [c["entity_id"] for c in comps],
        "culture_entity_ids": [c["entity_id"] for c in s.get("culture", [])],
    }


def poll(http: httpx.Client, path: str) -> dict[str, Any]:
    for _ in range(200):
        d = http.get(path).json()
        if d["status"] in ("done", "failed"):
            return d  # type: ignore[no-any-return]
        time.sleep(2)
    return d  # type: ignore[no-any-return]


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=180) as http:
        t = time.time()
        a = http.get("/v1/scout/activity").json()
        print(f"activity: {len(a['points'])} points, {a['calls']} in {time.time() - t:.1f}s")
        for lat, lon, title, desc, plats in JUDGE:
            t = time.time()
            r = http.post(
                "/v1/scout/judge",
                json={
                    "lat": lat,
                    "lon": lon,
                    "title": title,
                    "description": desc,
                    "platforms": plats,
                },
            )
            d = r.json()
            print(
                f"judge {title}: {d.get('verdict', d)} {d.get('calls', '')} in {time.time() - t:.1f}s"
            )
        for body in PLANS:
            pid = http.post("/v1/plans", json=body).json()["id"]
            p = poll(http, f"/v1/plans/{pid}")
            print(f"plan {body['game']['title']}: {p['status']} {p.get('calls')}")
        for s in SAMPLES:
            for city in s["cities"][:3]:
                d = http.post("/v1/scout/judge", json=from_plan(s, city)).json()
                print(
                    f"scout {s['input']['game']['title']} in {city['name']}: {d.get('verdict', d)} {d.get('calls', '')}"
                )
        rid = http.post("/v1/agent", json={"goal": AGENT_GOAL}).json()["id"]
        a = poll(http, f"/v1/agent/{rid}")
        print(f"agent: {a['status']} {a.get('answer_source')} {a.get('calls')}")


if __name__ == "__main__":
    main()
