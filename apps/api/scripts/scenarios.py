"""Accuracy scenarios: does the city ranking point where real players are?

Two sets of hypothetical games: the tuning set (scripts/scenarios.json, 10 games, the scorer was chosen
on it) and the held-out set (scripts/scenarios_holdout.json, frozen before it was ever scored). For each
we run S1-S3 on every candidate city with the scenario's comps (never the truth game), plus culture
anchors when the game has a setting, and compare the country ranking with Google Trends interest for a
real shipped analogue (trends_truth*.json, fetched by fetch_trends_truth.py). llm_baseline.py ranks the
same candidate countries with an LLM alone; its results are scored here by the same function.

  uv run python scripts/scenarios.py collect [scenarios file]  # live Qloo (cached 24h); writes scenario_raw*.json
  uv run python scripts/scenarios.py score                     # offline; writes docs/scenario-results.md and
                                                               # apps/web/public/eval-results.json
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
SETS = {"tuning": "scenarios.json", "holdout": "scenarios_holdout.json"}
# The tuning truth for Delhi Gullies never shipped (development was halted in 2026); reported both ways.
CANCELLED = {"delhi-gullies": "Mumbai Gullies, the truth analogue, never shipped"}
# The original S3 baseline (Minecraft, Fortnite, GTA V, Warzone), kept only to report how it compares.
MAINSTREAM = (
    "CDBDE254-71F0-4640-8D04-5373BEAE5278",
    "B335BB51-7158-4C34-89D1-4F1DB7CB5C01",
    "FEFD4E0D-D8F2-4BF9-86C9-06949DE82BCD",
    "B9318203-796E-4327-B161-5EEC584C382F",
)


def load(name: str) -> Any:
    return json.loads((HERE / name).read_text())


def paths(scenarios: str) -> tuple[Path, Path]:
    """scenarios_holdout.json -> (scenario_raw_holdout.json, trends_truth_holdout.json)."""
    suffix = scenarios.removeprefix("scenarios").removesuffix(".json")
    return HERE / f"scenario_raw{suffix}.json", HERE / f"trends_truth{suffix}.json"


def leaks(truth: dict[str, str], name: str) -> bool:
    """The truth game, or any game of its series, must never feed the signal."""
    series = resolve.normalize(truth.get("series", truth["title"]))
    return resolve.name_matches(truth["title"], name) or resolve.normalize(name).startswith(series)


async def collect(scenarios: str) -> None:
    s = get_settings()
    store = await Store.open(s.db_file)
    qloo = QlooClient(s, store)
    regions = cities.regions()
    out: dict[str, Any] = {"collected": date.today().isoformat(), "scenarios": {}}
    try:
        for sc in load(scenarios)["scenarios"]:
            run = qloo.run(max_calls=300)
            found, dropped = await resolve.resolve_names(run, sc["comps"])
            comps = [
                Comp(entity_id=f.resolved.entity_id, name=f.resolved.name, result_id="-")
                for f in found
                if f.resolved
            ]
            expanded = [
                g for g in await expand.expand(run, comps) if not leaks(sc["truth"], g.name)
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
    paths(scenarios)[0].write_text(json.dumps(out, indent=1) + "\n")


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
    "popularity": (
        "all gamers alone (mean of the PC, mobile, console panels): no game signal at all",
        lambda cs, _: {k: statistics.fmean(m["panels"].values()) for k, m in cs.items()},
    ),
}
DEFAULT = "spawn score"


def compare(
    sc: dict[str, Any], ours: dict[str, float], truth_all: dict[str, Any]
) -> dict[str, Any]:
    """One scenario's country scores vs Trends among the same candidate countries."""
    truth = {c: float(truth_all[sc["id"]].get(c, 0)) for c in ours}
    ranked = sorted(ours, key=lambda c: -ours[c])
    truth_top = max(truth, key=lambda c: truth[c])
    nonzero = [c for c in ours if truth[c] > 0]
    rho = (
        spearman([ours[c] for c in nonzero], [truth[c] for c in nonzero])
        if len(nonzero) >= 5
        else None
    )
    return {
        "id": sc["id"],
        "truth_top": truth_top,
        "truth_top3": sorted(truth, key=lambda c: -truth[c])[:3],
        "ours_top3": ranked[:3],
        "hit_top1": ranked[0] == truth_top,
        "hit_top3": truth_top in ranked[:3],
        "rho": None if rho is None else round(rho, 2),
        "n": len(nonzero),
    }


def candidates(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Cities Qloo returned data for: the candidate set every method ranks."""
    return {rid: m for rid, m in raw["cities"].items() if "skipped" not in m}


def evaluate(scorer: str, which: str = "tuning") -> list[dict[str, Any]]:
    """Country ranking = mean city score per country, compared with Trends among candidate countries."""
    raw_file, truth_file = paths(SETS[which])
    raw = json.loads(raw_file.read_text())["scenarios"]
    truth_all = json.loads(truth_file.read_text())
    regions = cities.regions()
    rows = []
    for sc in load(SETS[which])["scenarios"]:
        scores = SCORERS[scorer][1](candidates(raw[sc["id"]]), sc["platforms"])
        by_country: dict[str, list[float]] = {}
        for rid, v in scores.items():
            by_country.setdefault(regions[rid].country, []).append(v)
        row = compare(sc, {c: statistics.fmean(v) for c, v in by_country.items()}, truth_all)
        row["top_city"] = regions[max(scores, key=lambda r: scores[r])].name
        rows.append(row)
    return rows


def evaluate_llm(result_file: Path, which: str) -> list[dict[str, Any]]:
    """Score an llm_baseline.py ranking exactly like the city scorers (rank i of n scores n - i)."""
    ranks = json.loads(result_file.read_text())["rankings"]
    truth_all = json.loads(paths(SETS[which])[1].read_text())
    rows = []
    for sc in load(SETS[which])["scenarios"]:
        ranked = ranks[sc["id"]]
        rows.append(
            compare(sc, {c: float(len(ranked) - i) for i, c in enumerate(ranked)}, truth_all)
        )
    return rows


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rhos = [r["rho"] for r in rows if r["rho"] is not None]
    return {
        "n": len(rows),
        "top1": sum(r["hit_top1"] for r in rows),
        "top3": sum(r["hit_top3"] for r in rows),
        "rho": round(statistics.fmean(rhos), 2),
    }


def llm_results(which: str) -> dict[str, Path]:
    """llm_baseline_<set>_<model>.json files written by llm_baseline.py, by model label."""
    out = {}
    for f in sorted(HERE.glob(f"llm_baseline_{which}_*.json")):
        out[json.loads(f.read_text())["model"]] = f
    return out


def score() -> None:
    results: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for which in SETS:
        if not paths(SETS[which])[0].exists():
            continue
        results[which] = {name: evaluate(name, which) for name in SCORERS}
        for model, f in llm_results(which).items():
            results[which][f"LLM only ({model})"] = evaluate_llm(f, which)
        for name, rows in results[which].items():
            print(which, name, summary(rows))
    write_report(results)


def table_row(label: str, desc: str, s: dict[str, Any]) -> str:
    return f"| {label} | {desc} | {s['top1']}/{s['n']} | {s['top3']}/{s['n']} | {s['rho']} |"


def per_scenario(which: str, results: dict[str, list[dict[str, Any]]]) -> list[str]:
    raw = json.loads(paths(SETS[which])[0].read_text())["scenarios"]
    scen = {s["id"]: s for s in load(SETS[which])["scenarios"]}
    llms = [k for k in results if k.startswith("LLM only")]
    head = "| Scenario | Platforms | Comps | Culture anchors | Truth analogue | Truth top 3 | Crowdspawn top 3 | Our #1 city | Top-3 hit | ρ |"
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    for k in llms:
        head += f" {k} top 3 | LLM top-3 hit |"
        sep += "---|---|"
    lines = [head, sep]
    llm_rows = {k: {r["id"]: r for r in results[k]} for k in llms}
    for r in results[DEFAULT]:
        sc, d = scen[r["id"]], raw[r["id"]]
        truth = sc["truth"]["title"] + (" ‡" if r["id"] in CANCELLED else "")
        line = (
            f"| {sc['game']} | {', '.join(sc['platforms'])} | {', '.join(d['comps'])} | {', '.join(d['culture']) or 'none'} "
            f"| {truth} | {', '.join(r['truth_top3'])} | {', '.join(r['ours_top3'])} "
            f"| {r['top_city']} | {'yes' if r['hit_top3'] else 'no'} | {r['rho'] if r['rho'] is not None else 'n/a'} |"
        )
        for k in llms:
            lr = llm_rows[k][r["id"]]
            line += f" {', '.join(lr['ours_top3'])} | {'yes' if lr['hit_top3'] else 'no'} |"
        lines.append(line)
    return lines


def methods(results: dict[str, list[dict[str, Any]]], names: list[str]) -> list[dict[str, Any]]:
    """Headline rows for the web page: Crowdspawn, each LLM-only model, popularity."""
    label = {
        DEFAULT: "Crowdspawn (Qloo spawn score)",
        "popularity": "Popularity (all gamers, no game signal)",
    }
    return [{"method": label.get(k, k), **summary(results[k])} for k in names if k in results]


def write_report(results: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
    tuning = results["tuning"]
    holdout = results.get("holdout")
    llms = sorted({k for r in results.values() for k in r if k.startswith("LLM only")})
    headline = [DEFAULT, *llms, "popularity"]
    raw_t = json.loads(paths(SETS["tuning"])[0].read_text())
    lines = [
        "# Accuracy scenarios",
        "",
        "Does the city ranking point where real players are? We compare it with Google Trends interest by "
        "country for a *real shipped game* like each hypothetical one, and with two baselines: an LLM given "
        "the same inputs but no Qloo data, and plain gamer popularity. Scripts: `apps/api/scripts/scenarios.py`, "
        "`llm_baseline.py`, `fetch_trends_truth.py`. Numbers on this page are generated by `scenarios.py score`.",
        "",
        "**Method.** Each scenario is a hypothetical game with its own comps and, when the game has a setting, "
        "culture anchors (films, shows, artists) resolved through Qloo search. Each truth game is never used as "
        "a comp and is removed, with the rest of its series, from the expanded signal. Every candidate city "
        "is scored; country score = mean of its cities. Truth = Google Trends interest for the analogue "
        "(last 5 years), restricted to candidate countries. ρ = Spearman over candidate countries with Trends "
        "data (needs ≥ 5).",
        "",
    ]
    if holdout:
        raw_h = json.loads(paths(SETS["holdout"])[0].read_text())
        truth_h = json.loads(paths(SETS["holdout"])[1].read_text())
        n = len(holdout[DEFAULT])
        lines += [
            f"## 1. Held-out set ({n} games, no home-country setting)",
            "",
            f"Frozen in `scripts/scenarios_holdout.json` and committed before any held-out run; the scorer was "
            f"frozen at commit `{SCORER_SHA}`. Qloo data collected {raw_h['collected']}; Trends fetched "
            f"{truth_h['fetched']}. None of these games has a home-country setting, so neither method can lean "
            'on "a game set in Delhi sells in India".',
            "",
            "| Method | What it ranks by | Truth #1 is our #1 | Truth #1 in our top 3 | Mean ρ |",
            "|---|---|---|---|---|",
        ]
        lines += [
            table_row(
                k if k != DEFAULT else "**Crowdspawn** (`spawn score`)",
                SCORERS[k][0] if k in SCORERS else LLM_DESC,
                summary(holdout[k]),
            )
            for k in headline
            if k in holdout
        ]
        lines += ["", "### Per scenario", "", *per_scenario("holdout", holdout), ""]
    lines += [
        "## 2. Tuning set (10 games)",
        "",
        f"Qloo data collected {raw_t['collected']}; Trends fetched {load('trends_truth.json')['fetched']}. "
        "The scorer was chosen on these same games, so treat them as a sanity check, not a validation. "
        "‡ Delhi Gullies' truth analogue, Mumbai Gullies, never shipped (development was halted in 2026): "
        "**9 shipped games and 1 cancelled one**. Its Trends interest is pre-release search, so every metric "
        "is shown with and without it.",
        "",
        "| Scorer | What it ranks by | #1 hit (10) | Top-3 hit (10) | Mean ρ (10) | #1 hit (9 shipped) | Top-3 hit (9 shipped) | Mean ρ (9 shipped) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, rows in tuning.items():
        a, b = summary(rows), summary([r for r in rows if r["id"] not in CANCELLED])
        mark = " (shipped)" if name == DEFAULT else ""
        desc = SCORERS[name][0] if name in SCORERS else LLM_DESC
        lines.append(
            f"| `{name}`{mark} | {desc} | {a['top1']}/10 | {a['top3']}/10 | {a['rho']} "
            f"| {b['top1']}/9 | {b['top3']}/9 | {b['rho']} |"
        )
    lines += ["", f"### Per scenario (`{DEFAULT}`)", "", *per_scenario("tuning", tuning), ""]
    lines += [
        "## 3. Baselines",
        "",
        f"- **LLM only**: {LLM_DESC}. Prompt and code: `apps/api/scripts/llm_baseline.py`.",
        f'- **Popularity**: {SCORERS["popularity"][0]}. It shows how much of each ranking is just "where gamers are".',
        "",
        "## Caveats",
        "",
        "- Google Trends measures search interest share per country, not downloads, wishlists or sales.",
        "- Truth is country level; cities within a country are averaged. The app itself ranks cities.",
        "- Candidate countries are the app's markets with Qloo data, so places like Russia, Pakistan or Romania that top some Trends lists are outside every ranking.",
        "- Small samples: 10 tuning games and the held-out games above. One miss moves a hit rate by several points.",
        "- Each LLM ran once, at temperature 0, on one prompt. Another model or prompt could do better or worse.",
    ]
    (ROOT / "docs" / "scenario-results.md").write_text("\n".join(lines) + "\n")
    web: dict[str, Any] = {
        "generated_by": "apps/api/scripts/scenarios.py score",
        "tuning": {
            "n": 10,
            "methods": methods(tuning, headline),
            "shipped_only": methods(
                {k: [r for r in v if r["id"] not in CANCELLED] for k, v in tuning.items()}, headline
            ),
        },
    }
    if holdout:
        web["holdout"] = {"n": len(holdout[DEFAULT]), "methods": methods(holdout, headline)}
    WEB_JSON.write_text(json.dumps(web, indent=1, ensure_ascii=False) + "\n")
    print("wrote docs/scenario-results.md and", WEB_JSON.relative_to(ROOT))


LLM_DESC = (
    "an LLM given the same inputs (description, comps, culture anchors, platforms, candidate countries), "
    "no Qloo data, temperature 0, asked to rank the countries where such players most over-index"
)
WEB_JSON = ROOT / "apps" / "web" / "public" / "eval-results.json"
SCORER_SHA = "PENDING"  # the commit that froze this scorer before the held-out run


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["collect"]:
            asyncio.run(collect(SETS["tuning"]))
        case ["collect", name]:
            asyncio.run(collect(name))
        case ["score"]:
            score()
        case _:
            sys.exit(__doc__)
