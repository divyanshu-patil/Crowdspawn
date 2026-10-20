"""Scout "will my game work here?" from a description: LLM proposes names, Qloo does all the scoring.

1. The LLM turns the description into comparable games and culture anchors (names only).
2. Qloo resolves every name; unknown names are dropped, never invented.
3. Spawn score for the area and for 8 reference cities (same math as a plan: lift x platform x culture).
4. A verdict word from the spawn score, with stricter bands when confidence is lower.
5. The LLM writes a short explanation over the facts; numbers are checked, else a template is used.
"""

import asyncio
import json
from typing import Any

from pydantic import BaseModel, Field

from ..errors import AppError
from ..grounding import NUMBER, _to_float
from ..llm.base import LLMError, LLMProvider
from ..llm.structured import CallBudget, complete_json, render
from ..qloo.client import QlooRun
from ..schemas import Comp, CultureSuggestion, RankedPlace, ScoutJudge, VerdictBand
from ..settings import PANEL_TTL_SECONDS, PLATFORM_PANELS
from . import cities, culture, expand, resolve, scout
from .confidence import confidence
from .scoring import CityMetrics, spawn_scores

REFERENCE = ("nyc", "lon", "tyo", "sao", "del", "ist", "jkt", "syd")  # one per major market
# Verdict words (loot rarities) as spawn-score bands: the minimum score for each word, per confidence.
# Weaker evidence needs a stronger score; low confidence never reaches Legendary. The cut-offs reproduce
# the earlier probability-based verdicts (decisions log, 2026-10-20) without claiming a probability.
JUDGE_BANDS: dict[str, tuple[tuple[float, str], ...]] = {
    "high": ((1.149, "Legendary"), (1.079, "Epic"), (1.027, "Rare"), (0.975, "Uncommon")),
    "medium": ((1.310, "Legendary"), (1.114, "Epic"), (1.036, "Rare"), (0.966, "Uncommon")),
    "low": ((1.247, "Epic"), (1.055, "Rare"), (0.949, "Uncommon")),
}
LOWEST = "Common"


class Names(BaseModel):
    names: list[str] = Field(max_length=6)


class Anchors(BaseModel):
    anchors: list[CultureSuggestion] = Field(max_length=6)


class Summary(BaseModel):
    summary: str = Field(min_length=20, max_length=900)


def tier(score: float, conf: str) -> str:
    return next((word for cut, word in JUDGE_BANDS[conf] if score >= cut), LOWEST)


def bands(conf: str) -> list[VerdictBand]:
    return [VerdictBand(verdict=w, min_score=cut) for cut, w in JUDGE_BANDS[conf]]


def numbers_ok(text: str, facts: dict[str, Any]) -> bool:
    allowed = {_to_float(n) for n in NUMBER.findall(json.dumps(facts))}
    return all(_to_float(n) in allowed for n in NUMBER.findall(text))


def template(f: dict[str, Any]) -> str:
    drivers = f"taste lift {f['taste lift']} x platform fit {f['platform fit']}" + (
        f" x culture fit {f['culture fit']}" if f.get("culture fit") else ""
    )
    return (
        f"{f['verdict']} for {f['game']}: a spawn score of {f['spawn score']} ({drivers}) at "
        f"{f['confidence']} confidence. "
        f"It ranks {f['rank']} of {f['places compared']} places compared. "
        "This is an affinity estimate from Qloo taste data, not a sales forecast."
    )


async def suggest[T: BaseModel](
    llm: LLMProvider, budget: CallBudget, prompt: str, model: type[T], timeout: float
) -> T:
    out, _ = await complete_json(
        llm, [{"role": "user", "content": prompt}], model, budget, timeout=timeout
    )
    return out


async def judge(
    run: QlooRun,
    llm: LLMProvider,
    *,
    lat: float,
    lon: float,
    radius_km: int,
    title: str,
    description: str,
    tags: list[str],
    platforms: list[str],
    comp_ids: list[str],
    timeout: float,
    culture_ids: list[str] | None = None,
) -> ScoutJudge:
    budget = CallBudget(5)  # comps, culture, summary (+ one repair each where needed)
    game = {
        "title": title or "Your game",
        "description": description,
        "tags": ", ".join(tags) or "-",
    }

    # 1-2. LLM names -> Qloo entities. The culture step may fail quietly; comps may not.
    # A plan supplies every name (culture_ids set, even empty), so the LLM proposes none.
    from_plan = culture_ids is not None
    comp_names: Names | BaseException | None = None
    anchors: Anchors | BaseException | None = None
    if not from_plan:
        comp_names, anchors = await asyncio.gather(
            suggest(llm, budget, render("suggest_comps", **game), Names, timeout),
            suggest(llm, budget, render("suggest_culture", **game), Anchors, timeout),
            return_exceptions=True,
        )
    picked, _ = await resolve.lookup_comps(run, comp_ids) if comp_ids else ([], [])
    dropped: list[str] = []
    found: list[Comp] = list(picked)
    if isinstance(comp_names, Names):
        names = [n.strip() for n in comp_names.names if n.strip()]
        hits, miss = await resolve.resolve_names(run, names[:6])
        dropped += miss
        have = {c.entity_id for c in found}
        found += [
            Comp(entity_id=h.resolved.entity_id, name=h.resolved.name, result_id="-")
            for h in hits
            if h.resolved and h.resolved.entity_id not in have
        ]
    elif not found and not from_plan:
        raise comp_names if isinstance(comp_names, LLMError) else LLMError(str(comp_names))
    comps = found[:5]
    if not comps:
        raise AppError(
            "Qloo could not find games like the one you described. Add one or two by name.",
            code="comp_unresolved",
            status=422,
        )
    culture_names: list[str] = []
    if culture_ids:
        known, _ = await culture.lookup_culture(run, culture_ids)
        culture_ids, culture_names = [a.entity_id for a in known], [a.name for a in known]
    culture_ids = culture_ids or []
    if isinstance(anchors, Anchors) and anchors.anchors:
        pairs = list(
            dict.fromkeys((a.name.strip(), f"urn:entity:{a.type}") for a in anchors.anchors)
        )
        resolved, miss = await culture.resolve_culture(run, pairs[:5])
        dropped += miss
        culture_ids = [a.entity_id for a in resolved]
        culture_names = [a.name for a in resolved]

    # 3. Qloo: the area plus reference cities, scored together.
    signal = expand.signal_ids(comps, await expand.expand(run, comps))
    area, mix, _ = await scout.mix_widening(run, lat, lon, radius_km)
    refs = [
        r
        for rid, r in cities.regions().items()
        if rid in REFERENCE and scout_km(r.lat, r.lon, area.lat, area.lon) > 60
    ]

    async def metrics(r: Any, panels: dict[str, float] | None) -> tuple[CityMetrics, int]:
        jobs = [cities.heatmap_score(run, r, signal)]
        if culture_ids:
            jobs.append(cities.heatmap_score(run, r, culture_ids, PANEL_TTL_SECONDS))
        if panels is None:
            jobs += [
                cities.heatmap_score(run, r, ids, PANEL_TTL_SECONDS)
                for ids in PLATFORM_PANELS.values()
            ]
        heats = await asyncio.gather(*jobs)
        cult = heats[1][1] if culture_ids else None
        if panels is None:
            tail = heats[2:] if culture_ids else heats[1:]
            panels = dict(zip(PLATFORM_PANELS, (h[1] for h in tail), strict=True))
        return CityMetrics(
            target=heats[0][1], panels=panels, cells=heats[0][2], culture=cult
        ), heats[0][2]

    here_panels = {"pc": mix.pc, "mobile": mix.mobile, "console": mix.console}
    head = asyncio.gather(
        metrics(area, here_panels),
        scout.genre_heat(run, area, mix.general),
        scout.local_games(run, area),
    )
    tail = asyncio.gather(*(metrics(r, None) for r in refs))
    ((here, cells), genres, games), ref_metrics = await asyncio.gather(head, tail)
    all_metrics = {"here": here} | {r.name: m for r, (m, _) in zip(refs, ref_metrics, strict=True)}
    scores = spawn_scores(all_metrics, platforms)
    s = scores["here"]
    conf = confidence(s.score, cells)
    verdict = tier(s.score, conf)
    ranked = sorted(scores, key=lambda k: -scores[k].score)
    ranking = [
        RankedPlace(
            name="Here" if k == "here" else k, score=round(scores[k].score, 3), here=k == "here"
        )
        for k in ranked
    ]

    # 5. Explanation over facts only.
    facts = {
        "game": title or "your game",
        "verdict": verdict,
        "spawn score": f"{s.score:.2f}",
        "taste lift": f"{s.lift:.2f}",
        "platform fit": f"{s.platform_fit:.2f}",
        **({"culture fit": f"{s.culture_fit:.2f}"} if s.culture_fit is not None else {}),
        "confidence": conf,
        "rank": f"#{ranked.index('here') + 1}",
        "places compared": str(len(ranked)),
        "reference cities": [r.name for r in refs],
        "comparable games": [c.name for c in comps],
        "culture anchors": culture_names,
        "top genres here": [f"{g.genre} x{g.lift:.2f}" for g in genres[:3]],
        "local favourites": [g.name for g in games[:3]],
    }
    summary, source, model = template(facts), "template", None
    try:
        out, res = await complete_json(
            llm,
            [{"role": "user", "content": render("judge_summary", facts=json.dumps(facts))}],
            Summary,
            budget,
            timeout=timeout,
        )
        if numbers_ok(out.summary, facts):
            summary, source, model = out.summary, "llm", f"{res.provider} · {res.model}"
    except (LLMError, AppError):
        pass  # template stays

    return ScoutJudge(
        lat=area.lat,
        lon=area.lon,
        radius_km=area.radius_m // 1000,
        verdict=verdict,
        bands=bands(conf),
        score=round(s.score, 3),
        lift=round(s.lift, 3),
        platform_fit=round(s.platform_fit, 3),
        culture_fit=None if s.culture_fit is None else round(s.culture_fit, 3),
        confidence=conf,
        cells=cells,
        comps=[c.name for c in comps],
        culture=culture_names,
        dropped=dropped,
        ranking=ranking,
        genres=genres[:6],
        mix=mix,
        games=games[:6],
        summary=summary,
        summary_source=source,  # type: ignore[arg-type]
        model=model,
        calls=scout.calls(run),
    )


def scout_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return cities.km_between(lat1, lon1, lat2, lon2)
