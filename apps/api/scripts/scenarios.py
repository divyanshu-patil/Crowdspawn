"""Accuracy scenarios: does the city ranking point where real players are?

Ten independent hypothetical games (scripts/scenarios.json). For each we run S1-S3 on every candidate
city with the scenario's comps (never the truth game), plus culture anchors when the game has a setting,
and compare the country ranking with Google Trends interest for a real shipped analogue
(scripts/trends_truth.json, fetched by fetch_trends_truth.py).

  uv run python scripts/scenarios.py collect   # live Qloo (cached 24h); writes scripts/scenario_raw.json
  uv run python scripts/scenarios.py score     # offline; writes docs/scenario-results.md
"""

import asyncio
import json
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Any

from crowdspawn_api.errors import QlooError
from crowdspawn_api.pipeline import cities, expand, resolve
from crowdspawn_api.pipeline.culture import resolve_culture
from crowdspawn_api.pipeline.scoring import CityMetrics, spawn_scores
from crowdspawn_api.qloo.client import QlooClient
from crowdspawn_api.schemas import Comp
from crowdspawn_api.settings import PLATFORM_PANELS, get_settings
from crowdspawn_api.storage import Store

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RAW = HERE / "scenario_raw.json"
# The original S3 baseline (Minecraft, Fortnite, GTA V, Warzone), kept only to report how it compares.
MAINSTREAM = (
    "CDBDE254-71F0-4640-8D04-5373BEAE5278",
    "B335BB51-7158-4C34-89D1-4F1DB7CB5C01",
    "FEFD4E0D-D8F2-4BF9-86C9-06949DE82BCD",
    "B9318203-796E-4327-B161-5EEC584C382F",
)


def load(name: str) -> Any:
    return json.loads((HERE / name).read_text())


async def collect() -> None:
    s = get_settings()
    store = await Store.open(s.db_file)
    qloo = QlooClient(s, store)
    regions = cities.regions()
    out: dict[str, Any] = {"collected": date.today().isoformat(), "scenarios": {}}
    try:
        for sc in load("scenarios.json")["scenarios"]:
            run = qloo.run(max_calls=300)
            found, dropped = await resolve.resolve_names(run, sc["comps"])
            comps = [
                Comp(entity_id=f.resolved.entity_id, name=f.resolved.name, result_id="-")
                for f in found
                if f.resolved
            ]
            truth = sc["truth"]["title"]
            expanded = [  # no leakage: the truth game never feeds the signal
                g
                for g in await expand.expand(run, comps)
                if not resolve.name_matches(truth, g.name)
            ]
            signal = expand.signal_ids(comps, expanded)
            anchors, culture_dropped = await resolve_culture(run, [tuple(c) for c in sc["culture"]])
            per_city: dict[str, Any] = {}
            for rid, region in regions.items():
                try:
                    _, target, cells = await cities.heatmap_score(run, region, signal)
                    _, base, _ = await cities.heatmap_score(run, region, MAINSTREAM)
                    panels = {
                        p: (await cities.heatmap_score(run, region, ids))[1]
                        for p, ids in PLATFORM_PANELS.items()
                    }
                    culture = None
                    if anchors:
                        _, culture, _ = await cities.heatmap_score(
                            run, region, [a.entity_id for a in anchors]
                        )
                except QlooError as e:
                    per_city[rid] = {"skipped": e.detail}
                    continue
                per_city[rid] = {
                    "target": target,
                    "base": base,
                    "panels": panels,
                    "cells": cells,
                    "culture": culture,
                }
            out["scenarios"][sc["id"]] = {
                "comps": [c.name for c in comps],
                "dropped": dropped,
                "expanded": [g.name for g in expanded[: expand.SIGNAL_EXTRA]],
                "culture": [a.name for a in anchors],
                "culture_dropped": culture_dropped,
                "cities": per_city,
                "calls": run.calls,
            }
            print(sc["id"], "calls", run.calls, "dropped", dropped, culture_dropped)
    finally:
        await qloo.aclose()
        await store.close()
    RAW.write_text(json.dumps(out, indent=1) + "\n")


def spearman(a: list[float], b: list[float]) -> float:
    def ranks(x: list[float]) -> list[float]:
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        i = 0
        while i < len(order):  # average ranks for ties
            j = i
            while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r

    return statistics.correlation(ranks(a), ranks(b))


def metrics_of(m: dict[str, Any], culture: bool = True) -> CityMetrics:
    return CityMetrics(
        target=m["target"],
        panels=m["panels"],
        cells=m["cells"],
        culture=m["culture"] if culture else None,
    )


def _score(platforms: bool, culture: bool) -> Any:
    def f(cs: dict[str, Any], plats: list[str]) -> dict[str, float]:
        scores = spawn_scores(
            {k: metrics_of(m, culture) for k, m in cs.items()}, plats if platforms else []
        )
        return {k: v.score for k, v in scores.items()}

    return f


SCORERS: dict[str, tuple[str, Any]] = {
    "original": (
        "comp fans ÷ mainstream gamers (Minecraft, Fortnite, GTA V, Warzone): the old ranking",
        lambda cs, _: {k: m["target"] / m["base"] for k, m in cs.items()},
    ),
    "presence": ("comp-fan affinity alone", lambda cs, _: {k: m["target"] for k, m in cs.items()}),
    "lift": ("comp fans ÷ all gamers (mean of PC, mobile, console panels)", _score(False, False)),
    "lift×platform": ("lift × platform fit", _score(True, False)),
    "lift×culture": ("lift × culture fit", _score(False, True)),
    "spawn score": ("lift × platform fit × culture fit", _score(True, True)),
}
DEFAULT = "spawn score"


def evaluate(scorer: str) -> list[dict[str, Any]]:
    """Country ranking = mean city score per country, compared with Trends among candidate countries."""
    raw = json.loads(RAW.read_text())["scenarios"]
    truth_all = load("trends_truth.json")
    regions = cities.regions()
    rows = []
    for sc in load("scenarios.json")["scenarios"]:
        data = raw[sc["id"]]
        live = {rid: m for rid, m in data["cities"].items() if "skipped" not in m}
        scores = SCORERS[scorer][1](live, sc["platforms"])
        by_country: dict[str, list[float]] = {}
        for rid, v in scores.items():
            by_country.setdefault(regions[rid].country, []).append(v)
        ours = {c: statistics.fmean(v) for c, v in by_country.items()}
        truth = {c: float(truth_all[sc["id"]].get(c, 0)) for c in ours}
        ranked = sorted(ours, key=lambda c: -ours[c])
        truth_top = max(truth, key=lambda c: truth[c])
        nonzero = [c for c in ours if truth[c] > 0]
        rho = (
            spearman([ours[c] for c in nonzero], [truth[c] for c in nonzero])
            if len(nonzero) >= 5
            else None
        )
        top_city = max(scores, key=lambda r: scores[r])
        rows.append(
            {
                "id": sc["id"],
                "truth_top": truth_top,
                "truth_top3": sorted(truth, key=lambda c: -truth[c])[:3],
                "ours_top3": ranked[:3],
                "top_city": regions[top_city].name,
                "hit_top1": ranked[0] == truth_top,
                "hit_top3": truth_top in ranked[:3],
                "rho": None if rho is None else round(rho, 2),
                "n": len(nonzero),
            }
        )
    return rows


def summary(rows: list[dict[str, Any]]) -> dict[str, float]:
    rhos = [r["rho"] for r in rows if r["rho"] is not None]
    return {
        "top1": sum(r["hit_top1"] for r in rows),
        "top3": sum(r["hit_top3"] for r in rows),
        "rho": round(statistics.fmean(rhos), 2),
    }


def score() -> None:
    results = {name: evaluate(name) for name in SCORERS}
    for name, rows in results.items():
        print(name, summary(rows))
    write_report(results)


def write_report(results: dict[str, list[dict[str, Any]]]) -> None:
    raw = json.loads(RAW.read_text())
    scen = {s["id"]: s for s in load("scenarios.json")["scenarios"]}
    final = results[DEFAULT]
    lines = [
        "# Accuracy scenarios",
        "",
        f"Qloo data collected {raw['collected']}; Google Trends truth fetched {load('trends_truth.json')['fetched']} "
        "(interest by country, last 5 years). Scripts: `apps/api/scripts/scenarios.py`, `fetch_trends_truth.py`.",
        "",
        "**Method.** Ten independent hypothetical games, each with its own comps and, when the game has a setting, "
        "culture anchors (films, shows, artists) resolved through Qloo search. Each truth is a *real shipped game* "
        "that is never used as a comp and is removed from the expanded signal. Every candidate city is scored; "
        "country score = mean of its cities. Truth = Google Trends interest for the analogue, restricted to "
        "candidate countries. ρ = Spearman over candidate countries with Trends data (needs ≥ 5).",
        "",
        "## Scorers compared",
        "",
        "| Scorer | What it ranks by | Truth #1 is our #1 | Truth #1 in our top 3 | Mean ρ |",
        "|---|---|---|---|---|",
    ]
    for name, rows in results.items():
        s = summary(rows)
        mark = " (shipped)" if name == DEFAULT else ""
        lines.append(
            f"| `{name}`{mark} | {SCORERS[name][0]} | {s['top1']}/10 | {s['top3']}/10 | {s['rho']} |"
        )
    lines += [
        "",
        f"## Per scenario (`{DEFAULT}`)",
        "",
        "| Scenario | Platforms | Comps | Culture anchors | Truth analogue | Truth top 3 | Our top 3 | Our #1 city | Top-3 hit | ρ |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in final:
        d = raw["scenarios"][r["id"]]
        lines.append(
            f"| {scen[r['id']]['game']} | {', '.join(scen[r['id']]['platforms'])} | {', '.join(d['comps'])} | {', '.join(d['culture']) or 'none'} "
            f"| {scen[r['id']]['truth']['title']} | {', '.join(r['truth_top3'])} | {', '.join(r['ours_top3'])} "
            f"| {r['top_city']} | {'yes' if r['hit_top3'] else 'no'} | {r['rho'] if r['rho'] is not None else 'n/a'} |"
        )
    lines += [
        "",
        "## Caveats",
        "",
        "- Google Trends measures search interest share per country, not downloads or sales.",
        "- Truth is country level; cities within a country are averaged.",
        "- Candidate countries are the app's 21 markets, so places like Russia, Pakistan or Romania that top some Trends lists are outside the ranking.",
        "- Ten scenarios is a small sample, and the scorer weights were chosen on these same scenarios: treat the numbers as a sanity check, not a validation.",
    ]
    (ROOT / "docs" / "scenario-results.md").write_text("\n".join(lines) + "\n")
    print("wrote docs/scenario-results.md")


if __name__ == "__main__":
    if sys.argv[1:] == ["collect"]:
        asyncio.run(collect())
    elif sys.argv[1:] == ["score"]:
        score()
    else:
        sys.exit(__doc__)
