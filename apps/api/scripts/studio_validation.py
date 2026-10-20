"""Compare a plan's country ranking with a studio's real numbers by country (J20). No Qloo or LLM calls.

Usage: uv run python scripts/studio_validation.py <plan_id | plan.json> <values.csv> [slug]

values.csv has a header and two columns, `country_code,value`: ISO 3166-1 alpha-2 codes (US, JP, TR)
and one number per country, for example wishlists or units sold. To make it from Steamworks, export
the by-country report for the game, keep the country column and one numeric column, convert country
names to two-letter codes, and save it as CSV. Keep raw studio files under apps/api/data/studio/,
which git ignores; never commit them. Only the summary below is written to docs/.

A country's score is the mean of its cities' spawn scores, the same as scripts/scenarios.py, and
the same compare() gives top-1, top-3 and Spearman over the countries both sides cover.
"""

import asyncio
import csv
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

from scenarios import compare

from crowdspawn_api.settings import get_settings
from crowdspawn_api.storage import Store

ROOT = Path(__file__).resolve().parents[3]


async def plan_from_db(plan_id: str) -> dict[str, Any]:
    store = await Store.open(get_settings().db_file)
    try:
        row = await store.get_plan(plan_id)
    finally:
        await store.close()
    if not row or row["status"] != "done":
        raise SystemExit(f"no finished plan {plan_id!r}")
    result: dict[str, Any] = row["result"]
    return result


def load_plan(ref: str) -> dict[str, Any]:
    path = Path(ref)
    if path.suffix == ".json" and path.exists():
        plan: dict[str, Any] = json.loads(path.read_text())
        return plan
    return asyncio.run(plan_from_db(ref))


def read_values(path: Path) -> dict[str, float]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or not {"country_code", "value"} <= set(rows[0]):
        raise SystemExit("the CSV needs a header row: country_code,value")
    return {
        r["country_code"].strip().upper(): float(r["value"]) for r in rows if r["value"].strip()
    }


def country_scores(plan: dict[str, Any]) -> dict[str, float]:
    by: dict[str, list[float]] = {}
    for c in plan["cities"]:
        by.setdefault(c["country"], []).append(c["score"])
    return {k: statistics.fmean(v) for k, v in by.items()}


def report(plan: dict[str, Any], values: dict[str, float]) -> str:
    ours = country_scores(plan)
    covered = {c: s for c, s in ours.items() if c in values}
    if len(covered) < 2:
        raise SystemExit("fewer than 2 of the plan's countries are in the CSV")
    r = compare({"id": "studio"}, covered, {"studio": values})
    title = plan["input"]["game"]["title"]
    rho = "n/a (fewer than 5 countries with a value above 0)" if r["rho"] is None else r["rho"]
    rows = "\n".join(
        f"| {c} | {ours[c]:.3f} | {values[c]:g} |" for c in sorted(covered, key=lambda c: -ours[c])
    )
    return f"""# Studio validation: {title}

Crowdspawn's country ranking for this plan against the studio's own numbers by country. A country's
score is the mean of its cities' spawn scores. Only countries in both are compared ({len(covered)}).

| Check | Result |
|---|---|
| Studio's #1 country | {r["truth_top"]} |
| Crowdspawn's top 3 | {", ".join(r["ours_top3"])} |
| Studio's #1 is our #1 | {"yes" if r["hit_top1"] else "no"} |
| Studio's #1 is in our top 3 | {"yes" if r["hit_top3"] else "no"} |
| Spearman ρ | {rho} |

| Country | Crowdspawn score | Studio value |
|---|---|---|
{rows}

One game is one data point. The spawn score is an affinity index, not a sales forecast.
"""


def main(ref: str, csv_path: str, slug: str | None) -> None:
    plan = load_plan(ref)
    md = report(plan, read_values(Path(csv_path)))
    name = slug or re.sub(r"[^a-z0-9]+", "-", plan["input"]["game"]["title"].lower()).strip("-")
    out = ROOT / "docs" / "studio-validation" / f"{name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
