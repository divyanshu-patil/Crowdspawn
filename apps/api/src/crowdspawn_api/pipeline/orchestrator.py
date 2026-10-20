"""Runs S1..S8 for one plan, emitting progress events. Fails closed on any Qloo failure."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from ..errors import AppError, QlooBudgetExceeded, QlooDailyCap, QlooError, QlooUnconfigured
from ..llm.base import LLMProvider
from ..llm.structured import CallBudget
from ..qloo.client import QlooClient
from ..qloo.trace import TraceEntry
from ..schemas import Calls, Plan, PlanIn, Problem, Warning_
from ..settings import Settings
from ..storage import Store
from . import brief, budget, cities, compare, culture, demographics, expand, partners, resolve

log = logging.getLogger(__name__)

STEPS = {
    "S1": "Resolve comps",
    "S2": "Expand comp set",
    "S3": "Score cities: taste, platform, culture",
    "S4": "Read the audience",
    "S5": "Find partners",
    "S6": "Gap view",
    "S7": "Split the budget",
    "S8": "Write the brief",
}
LIMITS = [
    "Affinity index, not a sales forecast.",
    "Qloo measures taste affinity from consumption data, not sales or wishlists.",
    "New indie games are usually not in Qloo yet, so the plan works through comparable games.",
    "City-level results cannot be validated with free public data.",
    "Brands are global: Qloo brand affinity ignores location.",
    "Spawn score = taste lift x platform fit x culture fit, all from Qloo heatmaps.",
    "Accuracy: on held-out games with no real-world setting, an LLM without Qloo data found the top "
    "country (by Google Trends) more often than this ranking, which has a city-level bias. It does "
    "better when the game has a real-world setting. A Steam-review backtest on 6 shipped games also lost "
    "to plain popularity. Numbers: docs/scenario-results.md and docs/backtest-results.md.",
    "Treat the ranking as a taste-informed starting hypothesis and test it with small campaigns.",
    "Launch actions: languages come from a static table, not Qloo. The geo-target radius is the one "
    "Qloo's heatmap used.",
]


@dataclass
class Deps:
    settings: Settings
    store: Store
    qloo: QlooClient
    llm: LLMProvider | None


def created_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat()


async def run_plan(plan_id: str, req: PlanIn, deps: Deps) -> None:
    store = deps.store
    warnings: list[Warning_] = []

    async def emit(type_: str, data: dict[str, Any]) -> None:
        await store.add_event(plan_id, type_, data)

    async def on_call(e: TraceEntry) -> None:
        await emit(
            "qloo_call",
            {
                "result_id": e.result_id,
                "step": e.step,
                "endpoint": e.endpoint,
                "cache_hit": e.cache_hit,
                "duration_ms": e.duration_ms,
                "status": e.status,
            },
        )

    async def step(key: str) -> None:
        await emit("step_started", {"step": key, "label": STEPS[key]})

    async def done(key: str, summary: str) -> None:
        await emit("step_done", {"step": key, "summary": summary})

    async def warn(w: Warning_) -> None:
        warnings.append(w)
        await emit("warning", w.model_dump())

    run = deps.qloo.run(on_call)
    await store.set_status(plan_id, "running")
    try:
        if not deps.qloo.configured:
            raise QlooUnconfigured("Set QLOO_API_KEY in apps/api/.env")

        await step("S1")
        comps, missing = await resolve.lookup_comps(run, req.comp_entity_ids)
        for m in missing:
            await warn(
                Warning_(code="unresolved_comp", message=f"Comp {m} is not a Qloo video game")
            )
        if not comps:
            raise AppError(
                "None of the comps resolved to a Qloo video game",
                code="comp_unresolved",
                status=422,
            )
        anchors, missing_anchors = await culture.lookup_culture(run, req.culture_entity_ids)
        for m in missing_anchors:
            await warn(
                Warning_(
                    code="unresolved_culture",
                    message=f"Culture anchor {m} is not a Qloo film, show or artist",
                )
            )
        await done(
            "S1",
            f"{len(comps)} comps resolved"
            + (f", {len(anchors)} culture anchors" if anchors else ""),
        )

        await step("S2")
        expanded = await expand.expand(run, comps)
        signal = expand.signal_ids(comps, expanded)
        await done("S2", f"{len(expanded)} similar games")

        await step("S3")
        ranked, city_warnings = await cities.score_cities(
            run, req.regions, signal, list(req.platforms), [a.entity_id for a in anchors]
        )
        for w in city_warnings:
            await warn(w)
        if not ranked:
            raise QlooError("No city could be scored")
        await done("S3", f"Top city: {ranked[0].name} (score {ranked[0].score:.2f})")

        await step("S4")
        aud = await demographics.audience(run, signal)
        await done("S4", "Age and gender skew")

        await step("S5")
        names = {c.entity_id: c.name for c in comps} | {g.entity_id: g.name for g in expanded}
        found = await partners.partners(run, signal, names, ranked)
        await done("S5", f"{sum(len(getattr(found, k)) for k in partners.ALL_TYPES)} partners")

        gap = None
        if req.previous_game_entity_ids:
            await step("S6")
            gap = await compare.gap(run, req.previous_game_entity_ids, [c.entity_id for c in comps])
            await done("S6", f"{len(gap.target_only)} target-only tags")

        await step("S7")
        ranked = budget.split_budget(ranked, req.budget_usd)
        await done("S7", "Budget split by spawn score x confidence")

        row = await store.get_plan(plan_id)
        entries = run.trace.entries
        plan = Plan(
            id=plan_id,
            status="done",
            input=req,
            comps=comps,
            dropped_comps=missing,
            culture=anchors,
            expanded=expanded,
            cities=ranked,
            hidden_markets=cities.hidden_markets(ranked),
            audience=aud,
            partners=found,
            gap=gap,
            warnings=warnings,
            limits=LIMITS,
            created_at=created_iso(row["created_at"] if row else 0),
            calls=Calls(
                live=sum(not e.cache_hit for e in entries), cached=sum(e.cache_hit for e in entries)
            ),
        )

        await step("S8")
        s = deps.settings
        plan.brief = await brief.write_brief(
            plan,
            deps.llm,
            CallBudget(s.llm_max_calls_per_plan),
            run.trace.ids(),
            max_tokens=s.llm_max_output_tokens,
            timeout=s.llm_timeout_seconds,
        )
        if plan.brief.notice:
            await warn(Warning_(code="brief_template", message=plan.brief.notice))
            plan.warnings = warnings
        await done("S8", f"Brief from {plan.brief.source}")

        await store.save_trace(plan_id, run.trace.dump())
        await store.set_status(plan_id, "done", result=plan.model_dump(mode="json"))
        await emit("done", {"plan_id": plan_id})
    except ValidationError as e:  # Qloo body did not match the verified contract
        log.warning("plan %s: unexpected Qloo shape: %s", plan_id, str(e)[:300])
        await fail(
            deps,
            plan_id,
            run.trace.dump(),
            "qloo_bad_response",
            "Qloo returned a response in an unexpected shape",
        )
    except AppError as e:
        if isinstance(e, QlooBudgetExceeded | QlooDailyCap):
            await warn(
                Warning_(
                    code="partial_results",
                    message="Stopped at the call budget; partial results discarded.",
                )
            )
        await fail(deps, plan_id, run.trace.dump(), e.code, e.detail)
    except Exception:  # never leave a plan stuck in "running"
        log.exception("plan %s crashed", plan_id)
        await fail(deps, plan_id, run.trace.dump(), "internal_error", "Unexpected server error")


async def fail(deps: Deps, plan_id: str, trace: list[dict[str, Any]], code: str, msg: str) -> None:
    """Fail closed: keep the trace for transparency, store no plan data and no brief."""
    await deps.store.save_trace(plan_id, trace)
    await deps.store.set_status(
        plan_id, "failed", error=Problem(code=code, message=msg).model_dump()
    )
    await deps.store.add_event(plan_id, "failed", {"code": code, "message": msg})
