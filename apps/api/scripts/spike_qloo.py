"""Phase 0 spike: resolution rate, ranking sensitivity, strategy choice.

Live calls (~110). Writes fixtures under tests/fixtures/qloo/spike/ and prints a report.
Run: uv run python scripts/spike_qloo.py
"""

import asyncio
import json
import statistics
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from record_fixture import env  # type: ignore[import-not-found]  # noqa: E402

from crowdspawn_api.pipeline.resolve import name_matches  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "qloo" / "spike"
CITIES = json.loads((ROOT / "src/crowdspawn_api/data/cities.json").read_text())[:15]

INDIE_TITLES = [
    "Balatro",
    "Animal Well",
    "UFO 50",
    "Pacific Drive",
    "Lorelei and the Laser Eyes",
    "Nine Sols",
    "Tiny Glade",
    "Hades II",
    "Blue Prince",
    "Schedule I",
    "Peak",
    "Dispatch",
    "Mouthwashing",
    "Caves of Qud",
    "Neva",
    "Hollow Knight: Silksong",
    "Megabonk",
    "Ball x Pit",
    "Despelote",
    "Thronefall",
]
COZY = ["Stardew Valley", "Unpacking", "A Short Hike"]
ROGUE = ["Hades", "Dead Cells", "Slay the Spire"]
BASELINE = ["Minecraft", "Fortnite", "Grand Theft Auto V", "Call of Duty: Warzone"]

E = env()
calls = 0


async def get(c: httpx.AsyncClient, path: str, params: dict[str, str], name: str) -> dict:
    global calls
    calls += 1
    await asyncio.sleep(0.3)  # sequential, ~3 rps
    r = await c.get(path, params=params)
    body = r.json()
    f = OUT / f"{name}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps(
            {"request": {"path": path, "params": params}, "status": r.status_code, "body": body},
            ensure_ascii=False,
        )
    )
    return body


async def resolve(c: httpx.AsyncClient, title: str) -> dict | None:
    slug = "".join(ch if ch.isalnum() else "_" for ch in title.lower())
    body = await get(
        c,
        "/search",
        {"query": title, "types": "urn:entity:videogame", "take": "5"},
        f"search/{slug}",
    )
    for hit in body.get("results", [])[:5]:
        if name_matches(title, hit["name"]):
            return hit
    return None


def spearman(a: list[float], b: list[float]) -> float:
    def rank(x: list[float]) -> list[float]:
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        for pos, i in enumerate(order):
            r[i] = float(pos)
        return r

    ra, rb = rank(a), rank(b)
    return statistics.correlation(ra, rb)


async def city_scores(c: httpx.AsyncClient, label: str, ids: list[str]) -> dict[str, dict]:
    out = {}
    for city in CITIES:
        loc = f"POINT({city['lon']} {city['lat']})"
        hm = await get(
            c,
            "/v2/insights",
            {
                "filter.type": "urn:heatmap",
                "signal.interests.entities": ",".join(ids),
                "filter.location": loc,
                "filter.location.radius": str(city["radius_m"]),
            },
            f"heatmap/{label}_{city['id']}",
        )
        cells = hm.get("results", {}).get("heatmap", [])
        ranks = [x["query"]["affinity_rank"] for x in cells]
        pl = await get(
            c,
            "/v2/insights",
            {
                "filter.type": "urn:entity:place",
                "signal.interests.entities": ",".join(ids),
                "filter.location": loc,
                "filter.location.radius": str(city["radius_m"]),
                "take": "10",
            },
            f"place/{label}_{city['id']}",
        )
        affs = [x["query"]["affinity"] for x in pl.get("results", {}).get("entities", [])]
        out[city["id"]] = {
            "heatmap": statistics.fmean(ranks) if ranks else 0.0,
            "heatmap_cells": len(cells),
            "place": statistics.fmean(affs) if affs else 0.0,
        }
    return out


async def main() -> None:
    async with httpx.AsyncClient(
        base_url=E["QLOO_BASE_URL"], timeout=30, headers={"X-Api-Key": E["QLOO_API_KEY"]}
    ) as c:
        print("== 1. Resolution rate")
        resolved = 0
        for t in INDIE_TITLES:
            hit = await resolve(c, t)
            resolved += hit is not None
            print(f"  {'OK ' if hit else '-- '} {t:28} -> {hit['name'] if hit else ''}")
        print(f"  resolved {resolved}/{len(INDIE_TITLES)}")

        sets = {}
        for label, names in [("cozy", COZY), ("rogue", ROGUE), ("base", BASELINE)]:
            ids = [h["entity_id"] for n in names if (h := await resolve(c, n))]
            sets[label] = ids
            print(f"  set {label}: {len(ids)}/{len(names)} resolved")

        print("== 2. City scores (12+ cities x 3 sets x 2 strategies)")
        scores = {k: await city_scores(c, k, v) for k, v in sets.items()}
        ids = [x["id"] for x in CITIES]
        report = {}
        for strat in ("heatmap", "place"):
            lift = {
                k: [scores[k][i][strat] / max(scores["base"][i][strat], 1e-9) for i in ids]
                for k in ("cozy", "rogue")
            }
            base = [scores["base"][i][strat] for i in ids]
            report[strat] = {
                "spearman_cozy_vs_rogue_lift": spearman(lift["cozy"], lift["rogue"]),
                "spearman_cozy_raw_vs_base": spearman(
                    [scores["cozy"][i][strat] for i in ids], base
                ),
                "spearman_rogue_raw_vs_base": spearman(
                    [scores["rogue"][i][strat] for i in ids], base
                ),
                "spearman_cozy_lift_vs_base": spearman(lift["cozy"], base),
                "spearman_rogue_lift_vs_base": spearman(lift["rogue"], base),
                "cozy_top5": [
                    ids[i] for i in sorted(range(len(ids)), key=lambda i: -lift["cozy"][i])[:5]
                ],
                "rogue_top5": [
                    ids[i] for i in sorted(range(len(ids)), key=lambda i: -lift["rogue"][i])[:5]
                ],
            }
            print(f"  [{strat}]", json.dumps(report[strat], indent=2))

        print("== 3. Partners and compare")
        sig = ",".join(sets["rogue"])
        for t in ("artist", "podcast", "movie", "brand"):
            body = await get(
                c,
                "/v2/insights",
                {
                    "filter.type": f"urn:entity:{t}",
                    "signal.interests.entities": sig,
                    "take": "5",
                    "feature.explainability": "true",
                },
                f"partners/{t}",
            )
            print(
                f"  {t}: {[e['name'] for e in body.get('results', {}).get('entities', [])]}"
                f" {body.get('errors', '')}"
            )
        lon = CITIES[7]
        for key in ("signal.location", "filter.location"):
            body = await get(
                c,
                "/v2/insights",
                {
                    "filter.type": "urn:entity:artist",
                    "signal.interests.entities": sig,
                    "take": "5",
                    key: f"POINT({lon['lon']} {lon['lat']})",
                    f"{key}.radius": "30000",
                },
                f"partners/artist_lon_{key.split('.')[0]}",
            )
            print(
                f"  artist+{key}: {[e['name'] for e in body.get('results', {}).get('entities', [])]}"
                f" {body.get('errors', '')}"
            )
        cmp = await get(
            c,
            "/v2/analysis/compare",
            {
                "a.signal.interests.entities": ",".join(sets["cozy"]),
                "b.signal.interests.entities": ",".join(sets["rogue"]),
                "take": "5",
            },
            "compare/cozy_rogue",
        )
        print("  compare:", json.dumps(cmp)[:600])

        (OUT / "report.json").write_text(
            json.dumps(
                {"scores": scores, "report": report, "resolved": resolved, "calls": calls}, indent=2
            )
        )
        print(f"== live calls: {calls}")


asyncio.run(main())
