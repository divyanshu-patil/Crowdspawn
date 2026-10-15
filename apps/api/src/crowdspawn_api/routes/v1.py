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

from ..errors import NotFound, QlooUnconfigured, RateLimited
from ..llm.base import LLMError
from ..llm.structured import CallBudget, complete_json, render
from ..pipeline import cities, resolve
from ..pipeline.orchestrator import LIMITS, Deps, created_iso, run_plan
from ..schemas import (
    EntityOut,
    Plan,
    PlanCreated,
    PlanIn,
    Problem,
    Region,
    SuggestIn,
    SuggestOut,
    TraceRow,
)

router = APIRouter(prefix="/v1")
SSE_POLL_SECONDS = 0.25
SSE_HEARTBEAT_SECONDS = 15
_plan_hits: dict[str, deque[float]] = defaultdict(deque)


def deps(request: Request) -> Deps:
    d: Deps = request.app.state.deps
    return d


class SuggestedNames(BaseModel):
    names: list[str] = Field(max_length=6)


@router.get("/regions", response_model=list[Region])
async def list_regions() -> list[Region]:
    return list(cities.regions().values())


@router.get("/entities/search", response_model=list[EntityOut])
async def search_entities(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=80)],
    type: Annotated[str, Query(pattern="^videogame$")] = "videogame",
) -> list[EntityOut]:
    return await resolve.search_games(deps(request).qloo.run(max_calls=1), q)


@router.post("/comps/suggest", response_model=SuggestOut)
async def suggest_comps(request: Request, body: SuggestIn) -> SuggestOut:
    d = deps(request)
    if not d.qloo.configured:
        raise QlooUnconfigured("Set QLOO_API_KEY in apps/api/.env")
    if d.llm is None:
        raise LLMError("No LLM provider is configured")
    prompt = render(
        "suggest_comps",
        title=body.title,
        description=body.description or "-",
        tags=", ".join(body.tags) or "-",
    )
    out, _ = await complete_json(
        d.llm,
        [{"role": "user", "content": prompt}],
        SuggestedNames,
        CallBudget(2),
        timeout=d.settings.llm_timeout_seconds,
    )
    names = [n for n in dict.fromkeys(n.strip() for n in out.names) if n][:6]
    found, dropped = await resolve.resolve_names(d.qloo.run(max_calls=6), names)
    return SuggestOut(suggestions=found, dropped=dropped)


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
    ip = request.client.host if request.client else "unknown"
    hits, now = _plan_hits[ip], time.time()
    while hits and hits[0] < now - 3600:
        hits.popleft()
    if len(hits) >= d.settings.plans_per_ip_per_hour:
        raise RateLimited()
    hits.append(now)
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
    last = int(request.headers.get("last-event-id") or 0)

    async def events() -> AsyncIterator[str]:
        nonlocal last
        quiet = 0.0
        yield "retry: 1500\n\n"
        while not await request.is_disconnected():
            batch = await store.events_after(plan_id, last)
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
