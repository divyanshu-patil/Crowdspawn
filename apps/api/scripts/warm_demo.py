"""Warm a running API before judging, so every demo input answers from cache.

Calls the public endpoints (local or deployed): the scout activity map, the judge for the demo places,
and full plans for the demo games. Costs Qloo and LLM calls once; repeats are cached.
Run: uv run python scripts/warm_demo.py [http://localhost:8000]
"""

import sys
import time

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
PLANS = [
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
            for _ in range(120):
                p = http.get(f"/v1/plans/{pid}").json()
                if p["status"] in ("done", "failed"):
                    break
                time.sleep(2)
            print(f"plan {body['game']['title']}: {p['status']} {p.get('calls')}")


if __name__ == "__main__":
    main()
