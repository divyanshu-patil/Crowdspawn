"""LLM-only comparison: what an LLM answers for the same inputs, with every name it gives checked in Qloo.

The LLM sees what the plan saw (description, comps, culture anchors, platforms, candidate cities) and no Qloo
data. Each partner it names is resolved with Qloo search and scored with the same lift as the plan's own
partners (comp fans' affinity / all gamers' affinity), so the two lists are measured on one scale.
"""

import asyncio
from statistics import median

from pydantic import BaseModel, Field

from ..llm.base import LLMProvider
from ..llm.structured import CallBudget, complete_json, render
from ..qloo.client import QlooRun
from ..qloo.models import EntityInsights, SearchResponse
from ..schemas import LLMOnly, LLMOnlyKind, LLMPick, PartnerType, Plan
from ..settings import PANEL_TTL_SECONDS
from .expand import signal_ids
from .partners import ALL_TYPES, GAMERS
from .resolve import name_matches

TAKE = 6
QLOO_CALLS = len(ALL_TYPES) * (TAKE + 2)  # one search per name, two lift calls per type


class Picks(BaseModel):
    """Every key required, so a reply with other key names is repaired instead of read as empty."""

    cities: list[str] = Field(max_length=40)
    artist: list[str] = Field(max_length=12)
    podcast: list[str] = Field(max_length=12)
    movie: list[str] = Field(max_length=12)
    brand: list[str] = Field(max_length=12)


async def ask(llm: LLMProvider, plan: Plan, timeout: float) -> tuple[Picks, str, str]:
    prompt = render(
        "llm_only",
        title=plan.input.game.title,
        description=plan.input.game.description or "-",
        platforms=", ".join(plan.input.platforms),
        comps=", ".join(c.name for c in plan.comps) or "-",
        culture=", ".join(c.name for c in plan.culture) or "none",
        # Alphabetical: the plan's order is Qloo's ranking and must not leak into the baseline.
        cities=", ".join(
            f"{c.region_id} ({c.name})" for c in sorted(plan.cities, key=lambda c: c.name)
        ),
        kinds="artists (musicians), podcasts, movies and brands",
    )
    out, res = await complete_json(
        llm,
        [{"role": "user", "content": prompt}],
        Picks,
        CallBudget(2),
        temperature=0.0,
        timeout=timeout,
    )
    return out, res.provider, res.model


async def resolve(run: QlooRun, kind: PartnerType, name: str) -> LLMPick:
    type_ = f"urn:entity:{kind}"
    _, body = await run.get("LLM", "/search", {"query": name, "types": type_, "take": "5"})
    for hit in SearchResponse.model_validate(body).results:
        if type_ in hit.types and name_matches(name, hit.name):
            return LLMPick(
                name=name, entity_id=hit.entity_id, qloo_name=hit.name, image_url=hit.image_url
            )
    return LLMPick(name=name)


async def score(run: QlooRun, kind: PartnerType, signal: list[str], picks: list[LLMPick]) -> None:
    """Fill in lift for the resolved picks, exactly as partners.fetch_kind does for Qloo's own list."""
    ids = list(dict.fromkeys(p.entity_id for p in picks if p.entity_id))
    if not ids:
        return
    base = {
        "filter.type": f"urn:entity:{kind}",
        "filter.entities": ",".join(ids),
        "take": str(len(ids)),
    }
    (rid, fans), (_, gamers) = await asyncio.gather(
        run.get("LLM", "/v2/insights", base | {"signal.interests.entities": ",".join(signal)}),
        run.get(
            "LLM", "/v2/insights", base | {"signal.interests.entities": GAMERS}, PANEL_TTL_SECONDS
        ),
    )
    f = {
        e.entity_id: e.query.affinity for e in EntityInsights.model_validate(fans).results.entities
    }
    g = {
        e.entity_id: e.query.affinity
        for e in EntityInsights.model_validate(gamers).results.entities
    }
    for p in picks:
        a, b = f.get(p.entity_id or ""), g.get(p.entity_id or "")
        if a and b:
            p.lift, p.result_id = round(a / b, 4), rid


def _median(xs: list[float]) -> float | None:
    return round(median(xs), 4) if xs else None


async def compare(llm: LLMProvider, run: QlooRun, plan: Plan, timeout: float) -> LLMOnly:
    picks, provider, model = await ask(llm, plan, timeout)
    known = {c.region_id for c in plan.cities}
    ranked = [r for r in dict.fromkeys(picks.cities) if r in known]
    ranked += [c.region_id for c in plan.cities if c.region_id not in ranked]  # left out: last
    signal = signal_ids(plan.comps, plan.expanded)

    async def one(kind: PartnerType) -> LLMOnlyKind:
        names = [n for n in dict.fromkeys(n.strip() for n in getattr(picks, kind)) if n][:TAKE]
        found = list(await asyncio.gather(*(resolve(run, kind, n) for n in names)))
        await score(run, kind, signal, found)
        ours = [p for p in getattr(plan.partners, kind) if p.city is None]
        ours_ids = {p.entity_id for p in ours}
        return LLMOnlyKind(
            kind=kind,
            picks=found,
            found=sum(p.entity_id is not None for p in found),
            median_lift=_median([p.lift for p in found if p.lift is not None]),
            qloo_median_lift=_median([p.lift for p in ours if p.lift is not None]),
            overlap=sum(p.entity_id in ours_ids for p in found if p.entity_id),
        )

    kinds = await asyncio.gather(*(one(k) for k in ALL_TYPES))
    return LLMOnly(
        plan_id=plan.id, provider=provider, model=model, cities=ranked, partners=list(kinds)
    )
