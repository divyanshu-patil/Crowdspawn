import asyncio
import json
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..errors import NotFound, QlooError, QlooUnconfigured, RateLimited
from ..llm.base import LLMError, LLMProvider
from ..llm.structured import CallBudget, complete_json, render
from ..pipeline import agent, ask, cities, culture, judge, llm_only, resolve, scout
from ..pipeline.orchestrator import LIMITS, Deps, created_iso, run_plan
from ..schemas import (
    ActivityOut,
    AgentIn,
    AgentRun,
    AskIn,
    AskOut,
    CultureSuggestion,
    EntityOut,
    LLMOnly,
    PlaceHit,
    Plan,
    PlanCreated,
    PlanIn,
    Problem,
    Region,
    ScoutArea,
    ScoutAreaIn,
    ScoutFit,
    ScoutFitIn,
    ScoutJudge,
    ScoutJudgeIn,
    SuggestIn,
    Suggestion,
    SuggestOut,
    TraceRow,
)

router = APIRouter(prefix="/v1")
SSE_POLL_SECONDS = 0.25
SSE_HEARTBEAT_SECONDS = 15
_plan_hits: dict[str, deque[float]] = defaultdict(deque)
_scout_hits: dict[str, deque[float]] = defaultdict(deque)
_ask_hits: dict[str, deque[float]] = defaultdict(deque)


def _limit(request: Request, book: dict[str, deque[float]], per_hour: int) -> None:
    ip = request.client.host if request.client else "unknown"
    hits, now = book[ip], time.time()
    while hits and hits[0] < now - 3600:
        hits.popleft()
    if len(hits) >= per_hour:
        raise RateLimited()
    hits.append(now)


def deps(request: Request) -> Deps:
    d: Deps = request.app.state.deps
    return d


class SuggestedNames(BaseModel):
    names: list[str] = Field(max_length=6)


class SuggestedAnchors(BaseModel):
    anchors: list[CultureSuggestion] = Field(max_length=6)


def _ready(d: Deps) -> LLMProvider:
    if not d.qloo.configured:
        raise QlooUnconfigured("Set QLOO_API_KEY in apps/api/.env")
    if d.llm is None:
        raise LLMError("No LLM provider is configured")
    return d.llm


@router.get("/regions", response_model=list[Region])
async def list_regions() -> list[Region]:
    return list(cities.regions().values())


@router.get("/entities/search", response_model=list[EntityOut])
async def search_entities(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=80)],
    type: Annotated[str, Query(pattern="^(videogame|culture)$")] = "videogame",
) -> list[EntityOut]:
    """`culture` searches films, TV shows and artists (culture anchors for a game's setting)."""
    if type == "culture":
        return await culture.search_culture(deps(request).qloo.run(max_calls=3), q)
    return await resolve.search_games(deps(request).qloo.run(max_calls=1), q)


@router.post("/comps/suggest", response_model=SuggestOut)
async def suggest_comps(request: Request, body: SuggestIn) -> SuggestOut:
    d = deps(request)
    llm = _ready(d)
    prompt = render(
        "suggest_comps",
        title=body.title,
        description=body.description or "-",
        tags=", ".join(body.tags) or "-",
    )
    out, _ = await complete_json(
        llm,
        [{"role": "user", "content": prompt}],
        SuggestedNames,
        CallBudget(2),
        timeout=d.settings.llm_timeout_seconds,
    )
    names = [n for n in dict.fromkeys(n.strip() for n in out.names) if n][:6]
    found, dropped = await resolve.resolve_names(d.qloo.run(max_calls=6), names)
    return SuggestOut(suggestions=found, dropped=dropped)


@router.post("/culture/suggest", response_model=SuggestOut)
async def suggest_culture(request: Request, body: SuggestIn) -> SuggestOut:
    """LLM proposes films, shows and artists from the game's setting; Qloo must resolve each one."""
    d = deps(request)
    llm = _ready(d)
    prompt = render(
        "suggest_culture",
        title=body.title,
        description=body.description or "-",
        tags=", ".join(body.tags) or "-",
    )
    out, _ = await complete_json(
        llm,
        [{"role": "user", "content": prompt}],
        SuggestedAnchors,
        CallBudget(2),
        timeout=d.settings.llm_timeout_seconds,
    )
    pairs = list(dict.fromkeys((a.name.strip(), f"urn:entity:{a.type}") for a in out.anchors))
    found, dropped = await culture.resolve_culture(d.qloo.run(max_calls=6), pairs[:5])
    names = {f.entity_id: n for f in found for n, _ in pairs if resolve.name_matches(n, f.name)}
    return SuggestOut(
        suggestions=[
            Suggestion(input_name=names.get(f.entity_id, f.name), resolved=f) for f in found
        ],
        dropped=dropped,
    )


@router.post("/plans", status_code=202, response_model=PlanCreated)
async def create_plan(request: Request, body: PlanIn, tasks: BackgroundTasks) -> PlanCreated:
    d = deps(request)
    unknown = [r for r in body.regions if r not in cities.regions()]
    if unknown:
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "regions"),
                    "msg": f"unknown regions {unknown}",
                    "type": "value_error",
                }
            ]
        )
    _limit(request, _plan_hits, d.settings.plans_per_ip_per_hour)
    plan_id = uuid.uuid4().hex[:12]
    await d.store.create_plan(plan_id, body.model_dump(mode="json"))
    await d.store.add_event(plan_id, "queued", {"plan_id": plan_id})
    tasks.add_task(run_plan, plan_id, body, d)
    return PlanCreated(id=plan_id, status="queued")


@router.get("/plans/{plan_id}", response_model=Plan)
async def get_plan(request: Request, plan_id: str) -> Plan:
    row = await deps(request).store.get_plan(plan_id)
    if not row:
        raise NotFound(f"No plan {plan_id}")
    if row["result"]:
        return Plan.model_validate(row["result"])
    return Plan(
        id=row["id"],
        status=row["status"],
        input=PlanIn.model_validate(row["input"]),
        limits=LIMITS,
        created_at=created_iso(row["created_at"]),
        error=Problem.model_validate(row["error"]) if row["error"] else None,
    )


@router.post("/plans/{plan_id}/llm-only", response_model=LLMOnly)
async def plan_llm_only(request: Request, plan_id: str) -> LLMOnly:
    """What an LLM alone answers for this plan's inputs, each name checked in Qloo. Cached per plan."""
    d = deps(request)
    plan = await get_plan(request, plan_id)
    if plan.status != "done":
        raise NotFound(f"Plan {plan_id} is not finished")
    key = f"llm-only:{plan_id}"
    if hit := await d.store.cache_get(key):
        return LLMOnly.model_validate(hit)
    llm = _ready(d)
    _limit(request, _plan_hits, d.settings.plans_per_ip_per_hour)
    run = d.qloo.run(max_calls=llm_only.QLOO_CALLS)
    out = await llm_only.compare(llm, run, plan, d.settings.llm_timeout_seconds)
    await d.store.cache_put(key, out.model_dump(mode="json"), 30 * 86400)
    return out


@router.post("/ask", response_model=AskOut)
async def ask_plan(request: Request, body: AskIn) -> AskOut:
    """Answer a question from one plan's Qloo facts only. No Qloo calls; the answer is grounding-checked."""
    d = deps(request)
    if d.llm is None:
        raise LLMError("No LLM provider is configured")
    _limit(request, _ask_hits, d.settings.scouts_per_ip_per_hour)
    return await ask.answer(d.llm, body.plan, body.question, d.settings.llm_timeout_seconds)


@router.get("/plans/{plan_id}/trace", response_model=list[TraceRow])
async def get_trace(request: Request, plan_id: str) -> list[TraceRow]:
    store = deps(request).store
    if not await store.get_plan(plan_id):
        raise NotFound(f"No plan {plan_id}")
    return [TraceRow.model_validate(e) for e in await store.get_trace(plan_id)]


@router.get(
    "/plans/{plan_id}/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_plan(request: Request, plan_id: str) -> StreamingResponse:
    store = deps(request).store
    if not await store.get_plan(plan_id):
        raise NotFound(f"No plan {plan_id}")
    return _sse(request, plan_id)


def _sse(request: Request, run_id: str) -> StreamingResponse:
    """Replay a plan's or agent run's events from SQLite, then follow until done or failed."""
    store = deps(request).store
    last = int(request.headers.get("last-event-id") or 0)

    async def events() -> AsyncIterator[str]:
        nonlocal last
        quiet = 0.0
        yield "retry: 1500\n\n"
        while not await request.is_disconnected():
            batch = await store.events_after(run_id, last)
            for seq, type_, data in batch:
                last = seq
                yield f"id: {seq}\nevent: {type_}\ndata: {json.dumps(data)}\n\n"
            if any(t in ("done", "failed") for _, t, _ in batch):
                return
            quiet = 0.0 if batch else quiet + SSE_POLL_SECONDS
            if quiet >= SSE_HEARTBEAT_SECONDS:
                quiet = 0.0
                yield ": keep-alive\n\n"
            await asyncio.sleep(SSE_POLL_SECONDS)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _qloo_ready(d: Deps) -> None:
    if not d.qloo.configured:
        raise QlooUnconfigured("Set QLOO_API_KEY in apps/api/.env")


def _no_data(e: QlooError) -> QlooError:
    if (
        e.code == "qloo_filter_ignored"
    ):  # no heatmap cells: open sea, desert, or Qloo has no data here
        return QlooError(
            "Qloo has no player data around this point. Try a town or city.",
            code="no_area_data",
            status=422,
        )
    return e


@router.get("/scout/places", response_model=list[PlaceHit])
async def scout_places(
    request: Request, q: Annotated[str, Query(min_length=2, max_length=80)]
) -> list[PlaceHit]:
    """Find a town, city or region by name (Qloo localities, with coordinates)."""
    d = deps(request)
    _qloo_ready(d)
    return await scout.search_places(d.qloo.run(max_calls=1), q)


@router.get("/scout/activity", response_model=ActivityOut)
async def scout_activity(request: Request) -> ActivityOut:
    """Player activity index (PC, mobile, console panels) for 67 cities. Cached for a week."""
    d = deps(request)
    _qloo_ready(d)
    run = d.qloo.run(max_calls=3 * len(scout.scout_points()))
    points, skipped = await scout.activity(run)
    return ActivityOut(points=points, skipped=skipped, calls=scout.calls(run))


@router.post("/scout/area", response_model=ScoutArea)
async def scout_area(request: Request, body: ScoutAreaIn) -> ScoutArea:
    """What works here: platform mix, genre heat and the games locals love."""
    d = deps(request)
    _qloo_ready(d)
    _limit(request, _scout_hits, d.settings.scouts_per_ip_per_hour)
    try:
        return await scout.scout_area(d.qloo.run(max_calls=24), body.lat, body.lon, body.radius_km)
    except QlooError as e:
        raise _no_data(e) from e


@router.post("/scout/fit", response_model=ScoutFit)
async def scout_fit(request: Request, body: ScoutFitIn) -> ScoutFit:
    """Would my game work here: spawn score of the comp set in this area."""
    d = deps(request)
    _qloo_ready(d)
    _limit(request, _scout_hits, d.settings.scouts_per_ip_per_hour)
    try:
        return await scout.scout_fit(
            d.qloo.run(max_calls=26),
            body.lat,
            body.lon,
            body.radius_km,
            body.comp_entity_ids,
            list(body.platforms),
        )
    except QlooError as e:
        raise _no_data(e) from e


@router.post("/scout/judge", response_model=ScoutJudge)
async def scout_judge(request: Request, body: ScoutJudgeIn) -> ScoutJudge:
    """Would the game I describe work here? LLM proposes names, Qloo scores, verdict from spawn-score bands."""
    d = deps(request)
    llm = _ready(d)
    _limit(request, _scout_hits, d.settings.scouts_per_ip_per_hour)
    try:
        return await judge.judge(
            d.qloo.run(max_calls=90),
            llm,
            lat=body.lat,
            lon=body.lon,
            radius_km=body.radius_km,
            title=body.title,
            description=body.description,
            tags=body.tags,
            platforms=list(body.platforms),
            comp_ids=body.comp_entity_ids,
            culture_ids=body.culture_entity_ids,
            timeout=d.settings.llm_timeout_seconds,
        )
    except QlooError as e:
        raise _no_data(e) from e


@router.post("/agent", status_code=202, response_model=PlanCreated)
async def start_agent(request: Request, body: AgentIn, tasks: BackgroundTasks) -> PlanCreated:
    """Start the launch agent: an LLM that plans with Qloo tools. Follow it on /agent/{id}/stream."""
    d = deps(request)
    _qloo_ready(d)
    _ready(d)
    _limit(request, _plan_hits, d.settings.plans_per_ip_per_hour)
    run_id = "a" + uuid.uuid4().hex[:11]
    await d.store.create_run(run_id, body.model_dump())
    await d.store.add_event(run_id, "queued", {"id": run_id})
    tasks.add_task(
        agent.run_agent,
        run_id,
        body.goal,
        d.store,
        d.qloo,
        d.llm,
        timeout=d.settings.llm_timeout_seconds,
    )
    return PlanCreated(id=run_id, status="running")


@router.get("/agent/{run_id}", response_model=AgentRun)
async def get_agent(request: Request, run_id: str) -> AgentRun:
    row = await deps(request).store.get_run(run_id)
    if not row:
        raise NotFound(f"No agent run {run_id}")
    if row["result"]:
        return AgentRun.model_validate(row["result"])
    return AgentRun(id=row["id"], status="running", goal=row["input"]["goal"])


@router.get(
    "/agent/{run_id}/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_agent(request: Request, run_id: str) -> StreamingResponse:
    if not await deps(request).store.get_run(run_id):
        raise NotFound(f"No agent run {run_id}")
    return _sse(request, run_id)
