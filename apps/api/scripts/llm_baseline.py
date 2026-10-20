"""LLM-only baseline: can a language model with no Qloo data rank the launch countries as well?

For every scenario the LLM gets exactly what the app gets (description, comps, culture anchors, platforms)
plus the same candidate countries the city ranking is scored on, at temperature 0, and returns a ranking.
scenarios.py scores it with the same function, against the same Google Trends truth. Uses the configured
LLM provider (LLM_PROVIDER in apps/api/.env), so the same script runs any model the app supports.

  uv run python scripts/llm_baseline.py [tuning|holdout]   # writes scripts/llm_baseline_<set>_<model>.json
  uv run python scripts/scenarios.py score                  # adds an "LLM only" row per model
"""

import asyncio
import json
import re
import sys
from datetime import date
from typing import Any

from pydantic import BaseModel
from scenarios import HERE, SETS, candidates, load, paths

from crowdspawn_api.llm.registry import build_provider, model_name
from crowdspawn_api.llm.structured import CallBudget, complete_json
from crowdspawn_api.pipeline import cities
from crowdspawn_api.settings import get_settings


class Ranking(BaseModel):
    ranking: list[str]


def prompt(sc: dict[str, Any], countries: list[str]) -> str:
    culture = ", ".join(n for n, _ in sc.get("culture", [])) or "none"
    return (
        "You are a games marketing analyst. A studio is launching this game:\n"
        f"Game: {sc['game']}\nPlatforms: {', '.join(sc['platforms'])}\n"
        f"Comparable games: {', '.join(sc['comps'])}\nCulture the setting draws on: {culture}\n\n"
        "Rank ALL of these countries (ISO codes) from the one where players of this kind of game most "
        "over-index (relative to the country's general gaming population) to the least:\n"
        f"{', '.join(countries)}\n\n"
        'Reply with JSON only: {"ranking": ["XX", ...]} containing every code exactly once.'
    )


async def main(which: str) -> None:
    s = get_settings()
    llm = build_provider(s)
    if llm is None:
        sys.exit("No LLM provider configured (LLM_PROVIDER in apps/api/.env)")
    raw = json.loads(paths(SETS[which])[0].read_text())["scenarios"]
    regions = cities.regions()
    out: dict[str, Any] = {"model": model_name(s), "ran": date.today().isoformat(), "rankings": {}}
    try:
        for sc in load(SETS[which])["scenarios"]:
            countries = sorted({regions[r].country for r in candidates(raw[sc["id"]])})
            msg, _ = await complete_json(
                llm,
                [{"role": "user", "content": prompt(sc, countries)}],
                Ranking,
                CallBudget(2),  # one repair attempt
                temperature=0.0,
                timeout=s.llm_timeout_seconds,
            )
            ranked = list(dict.fromkeys(c for c in msg.ranking if c in countries))
            ranked += [c for c in countries if c not in ranked]  # anything left out ranks last
            out["rankings"][sc["id"]] = ranked
            print(sc["id"], ranked[:3], flush=True)
    finally:
        await llm.aclose()
    slug = re.sub(r"[^a-z0-9]+", "-", out["model"].lower()).strip("-")
    (HERE / f"llm_baseline_{which}_{slug}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "tuning"))
