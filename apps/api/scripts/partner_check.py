"""Partner check: how do Qloo's partner lists differ from what an LLM alone suggests?

For 20 games (the 10 tuning games and the first 10 held-out ones) the LLM gets the same inputs as Qloo and
names 6 artists, podcasts, films and brands; Qloo's lists are its top 6 by lift, built exactly as a plan
builds them. Design fixed before any call (docs/10-risks-decisions.md, local). Metrics:

- specificity: the share of a method's names that recur in 3 or more of the 20 games (not scored by Qloo);
- found: the LLM's names that Qloo can resolve;
- lift of the LLM's names, scored by Qloo. Not independent: Qloo also picked its own list by lift.

  uv run python scripts/partner_check.py           # live: ~40 Qloo calls a game, 1 LLM call a game, + samples
  uv run python scripts/partner_check.py report    # offline: docs/partner-check.md, apps/web/public/partner-check.json
"""

import asyncio
import json
import sys
from collections import Counter
from datetime import date
from statistics import median
from typing import Any

from scenarios import HERE, ROOT, SETS, load

from crowdspawn_api.llm.registry import build_provider
from crowdspawn_api.pipeline import llm_only, partners, resolve
from crowdspawn_api.qloo.client import QlooClient
from crowdspawn_api.schemas import Comp, CultureAnchor, GameIn, Partners, Plan, PlanIn
from crowdspawn_api.settings import get_settings
from crowdspawn_api.storage import Store

OUT = HERE / "partner_check.json"
WEB = ROOT / "apps" / "web" / "public"
TAKE = llm_only.TAKE
KINDS = partners.ALL_TYPES
RECUR = 3  # a name in this many games or more counts as generic


def games() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = (
        load(SETS["tuning"])["scenarios"] + load(SETS["holdout"])["scenarios"][:10]
    )
    return out


async def collect() -> None:
    s = get_settings()
    store = await Store.open(s.db_file)
    qloo = QlooClient(s, store)
    llm = build_provider(s)
    if llm is None:
        sys.exit("No LLM provider configured")
    out: dict[str, Any] = {"collected": date.today().isoformat(), "games": {}}
    try:
        for sample in ("sample", "sample-delhi"):  # what the app shows on its two sample plans
            plan = Plan.model_validate(json.loads((WEB / f"{sample}-plan.json").read_text()))
            res = await llm_only.compare(
                llm, qloo.run(max_calls=llm_only.QLOO_CALLS), plan, s.llm_timeout_seconds
            )
            (WEB / f"{sample}-llm-only.json").write_text(res.model_dump_json(indent=1) + "\n")
            print(sample, "live so far", qloo.live_calls, flush=True)
        for sc in games():
            run = qloo.run(max_calls=llm_only.QLOO_CALLS + 20)
            found, _ = await resolve.resolve_names(run, sc["comps"])
            comps = [
                Comp(entity_id=f.resolved.entity_id, name=f.resolved.name, result_id="-")
                for f in found
                if f.resolved
            ]
            signal = [c.entity_id for c in comps]
            lists = await asyncio.gather(
                *(partners.fetch_kind(run, k, signal, {}, None) for k in KINDS)
            )
            title, _, desc = sc["game"].partition(": ")
            plan = Plan.model_construct(
                id=sc["id"],
                status="done",
                input=PlanIn.model_construct(
                    game=GameIn(title=title, description=desc), platforms=sc["platforms"]
                ),
                comps=comps,
                expanded=[],
                culture=[CultureAnchor.model_construct(name=n) for n, _ in sc.get("culture", [])],
                cities=[],
                partners=Partners(**{k: v[:TAKE] for k, v in zip(KINDS, lists, strict=True)}),
            )
            res = await llm_only.compare(llm, run, plan, s.llm_timeout_seconds)
            out["games"][sc["id"]] = {
                "game": sc["game"],
                "qloo": {
                    k: [{"name": p.name, "lift": p.lift} for p in v[:TAKE]]
                    for k, v in zip(KINDS, lists, strict=True)
                },
                "llm": {k.kind: [p.model_dump() for p in k.picks] for k in res.partners},
            }
            print(sc["id"], "live so far", qloo.live_calls, flush=True)
            OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    finally:
        await llm.aclose()
        await qloo.aclose()
        await store.close()


def report() -> None:
    d = json.loads(OUT.read_text())
    gs = list(d["games"].values())
    n = len(gs)

    def names(method: str, kind: str) -> list[set[str]]:
        key = "name" if method == "qloo" else "qloo_name"
        return [{(p.get(key) or p["name"]).casefold() for p in g[method][kind]} for g in gs]

    def generic(method: str, kind: str) -> tuple[float, list[str]]:
        sets = names(method, kind)
        counts = Counter(x for s in sets for x in s)
        slots = sum(len(s) for s in sets)
        common = [x for x, c in counts.most_common() if c >= RECUR]
        return (sum(counts[x] for x in common) / slots if slots else 0.0), common

    rows, web = [], []
    for kind in KINDS:
        q_share, q_common = generic("qloo", kind)
        l_share, l_common = generic("llm", kind)
        picks = [p for g in gs for p in g["llm"][kind]]
        found = [p for p in picks if p["entity_id"]]
        l_lifts = [p["lift"] for p in found if p["lift"] is not None]
        q_lifts = [p["lift"] for g in gs for p in g["qloo"][kind] if p["lift"] is not None]
        below = sum(lf <= 1 for lf in l_lifts)
        row = {
            "kind": kind,
            "qloo_generic_pct": round(100 * q_share),
            "llm_generic_pct": round(100 * l_share),
            "llm_found": len(found),
            "llm_picks": len(picks),
            "llm_median_lift": round(median(l_lifts), 3) if l_lifts else None,
            "qloo_median_lift": round(median(q_lifts), 3) if q_lifts else None,
            "llm_not_above_1": below,
            "llm_scored": len(l_lifts),
            "llm_most_repeated": l_common[:3],
            "qloo_most_repeated": [x for x in q_common[:3]],
        }
        web.append(row)
        rows.append(
            f"| {kind} | {row['qloo_generic_pct']}% | {row['llm_generic_pct']}% | {len(found)} of {len(picks)} "
            f"| ×{row['qloo_median_lift']} | ×{row['llm_median_lift']} | {below} of {len(l_lifts)} |"
        )
    llm_model = json.loads((WEB / "sample-llm-only.json").read_text())["model"]
    lines = [
        "# Partner check: Qloo vs an LLM alone",
        "",
        f"For {n} games (the 10 tuning games and the first 10 held-out ones) an LLM ({llm_model}, no Qloo data, "
        "temperature 0) and Qloo each name 6 artists, podcasts, films and brands that fans of the game's comps "
        "like more than gamers in general. Qloo's lists are built exactly as a plan builds them. Design fixed "
        f"before any call. Data collected {d['collected']}; `apps/api/scripts/partner_check.py` regenerates this page.",
        "",
        "| Type | Generic names: Qloo | Generic names: LLM | LLM names Qloo can find | Median lift: Qloo | Median lift: LLM's names | LLM's names gamers like as much (lift ≤ 1) |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        f"**Generic names** are the share of a method's names that it gives for {RECUR} or more of the {n} games: "
        "the same names whatever the game. This measure doesn't use Qloo's scores.",
        "",
        "Most repeated by the LLM: "
        + "; ".join(f"{r['kind']}s: {', '.join(r['llm_most_repeated']) or 'none'}" for r in web)
        + ".",
        "",
        "Most repeated by Qloo: "
        + "; ".join(f"{r['kind']}s: {', '.join(r['qloo_most_repeated']) or 'none'}" for r in web)
        + ".",
        "",
        "**Where Qloo's lists are more generic:** "
        + (
            ", ".join(
                f"{r['kind']}s ({r['qloo_generic_pct']}% vs {r['llm_generic_pct']}%)"
                for r in web
                if r["qloo_generic_pct"] > r["llm_generic_pct"]
            )
            or "none"
        )
        + ".",
        "",
        "## Caveats",
        "",
        "- Lift for the LLM's names is measured with Qloo's data, and Qloo chose its own list by lift, so Qloo "
        "wins that column by construction. It shows how far the LLM's picks sit from the measured audience; it is "
        "not an independent test.",
        "- Neither list is checked against real sponsorship results. A generic name can still be a good partner; "
        "it just isn't specific to this audience.",
        "- One LLM, one prompt, temperature 0. Names the LLM gave that Qloo couldn't resolve are counted as not found, "
        "even if they exist.",
    ]
    (ROOT / "docs" / "partner-check.md").write_text("\n".join(lines) + "\n")
    (WEB / "partner-check.json").write_text(
        json.dumps(
            {
                "collected": d["collected"],
                "games": n,
                "model": llm_model,
                "recur": RECUR,
                "rows": web,
            },
            indent=1,
        )
        + "\n"
    )
    for r in web:
        print(r)


if __name__ == "__main__":
    match sys.argv[1:]:
        case []:
            asyncio.run(collect())
            report()
        case ["report"]:
            report()
        case _:
            sys.exit(__doc__)
