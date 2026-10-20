"""The launch agent: an LLM that plans step by step with Qloo tools.

Each step the model returns {"thought", "tool", "args"}; the server runs the tool against Qloo and feeds
back a compact observation. Guards keep the "Qloo is the only data source" rule:
- entities are referred to by handles the server issued (g1, c2, p1), so the model cannot invent ids;
- the final answer may only use numbers and bold names that appeared in observations, or a template
  built from the last city ranking replaces it;
- caps: 10 steps, 12 LLM calls, 150 Qloo calls; auth, budget and rate-limit errors fail the run closed.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from ..errors import AppError, QlooError
from ..grounding import BOLD, EXTRA_CITIES, NUMBER, _to_float, city_numbers, misattributed
from ..llm.base import LLMError, LLMProvider
from ..llm.structured import CallBudget, complete_json, render
from ..qloo.client import QlooClient, QlooRun
from ..qloo.trace import TraceEntry
from ..schemas import (
    AgentRun,
    AgentStepOut,
    Calls,
    City,
    Comp,
    DraftCulture,
    DraftGame,
    PlanDraft,
    Platform,
    Problem,
)
from ..storage import Store
from . import cities, culture, demographics, expand, partners, resolve, scout

ALL_PLATFORMS: list[Platform] = ["pc", "mobile", "console"]

log = logging.getLogger(__name__)

MAX_STEPS = 10
MAX_LLM_CALLS = 12
MAX_QLOO_CALLS = 150
OBS_CHARS = 900
Tool = Literal[
    "search_games",
    "search_culture",
    "find_place",
    "rank_cities",
    "scout_place",
    "audience",
    "find_partners",
    "finish",
]


class Step(BaseModel):
    thought: str = Field(default="", max_length=600)
    tool: Tool
    args: dict[str, Any] = {}


class Query(BaseModel):
    query: str = Field(min_length=1, max_length=80)


class RankArgs(BaseModel):
    games: list[str] = Field(min_length=1, max_length=5)
    culture: list[str] = Field(default=[], max_length=5)
    platforms: list[Platform] = Field(default=ALL_PLATFORMS, min_length=1, max_length=3)
    cities: list[str] = Field(default=[], max_length=20)


class PlaceArgs(BaseModel):
    place: str


class GamesArgs(BaseModel):
    games: list[str] = Field(min_length=1, max_length=5)


class PartnerArgs(GamesArgs):
    city: str | None = None


class FinishArgs(BaseModel):
    answer: str = Field(min_length=20, max_length=1500)
    games: list[str] = []
    culture: list[str] = []
    platforms: list[Platform] = []
    cities: list[str] = []
    title: str = Field(default="Your game", max_length=80)


class ToolError(Exception):
    """A tool call the model can recover from: bad handle, bad args, empty result."""


@dataclass
class Memory:
    games: dict[str, tuple[str, str]] = field(default_factory=dict)  # g1 -> (entity_id, name)
    culture: dict[str, tuple[str, str, str]] = field(default_factory=dict)  # c1 -> (id, name, type)
    places: dict[str, tuple[str, float, float]] = field(
        default_factory=dict
    )  # p1 -> (name, lat, lon)
    signals: dict[tuple[str, ...], list[str]] = field(default_factory=dict)
    ranking: list[City] = field(default_factory=list)
    rank_args: RankArgs | None = None
    observations: list[str] = field(default_factory=list)

    def handle(self, kind: str, store: dict[str, Any]) -> str:
        return f"{kind}{len(store) + 1}"

    def game_ids(self, handles: list[str]) -> list[str]:
        bad = [h for h in handles if h not in self.games]
        if bad:
            raise ToolError(f"unknown game handles {bad}; use search_games first")
        return [self.games[h][0] for h in dict.fromkeys(handles)]

    def culture_ids(self, handles: list[str]) -> list[str]:
        bad = [h for h in handles if h not in self.culture]
        if bad:
            raise ToolError(f"unknown culture handles {bad}; use search_culture first")
        return [self.culture[h][0] for h in dict.fromkeys(handles)]


def city_ids(ids: list[str]) -> list[str]:
    known = cities.regions()
    bad = [i for i in ids if i not in known]
    if bad:
        raise ToolError(f"unknown city ids {bad}")
    return list(dict.fromkeys(ids))


DEFAULT_CITIES = [r.id for r in cities.regions().values() if r.default]


async def signal_for(run: QlooRun, mem: Memory, game_ids: list[str]) -> list[str]:
    """Comps plus Qloo's closest similar games (as in a plan), cached per comp set."""
    key = tuple(sorted(game_ids))
    if key not in mem.signals:
        names = {gid: n for gid, n in mem.games.values()}
        comps = [Comp(entity_id=g, name=names.get(g, g), result_id="-") for g in game_ids]
        mem.signals[key] = expand.signal_ids(comps, await expand.expand(run, comps))
    return mem.signals[key]


def fmt_city(c: City) -> str:
    parts = f"taste {c.lift:.2f} x platform {c.platform_fit:.2f}" + (
        f" x culture {c.culture_fit:.2f}" if c.culture_fit is not None else ""
    )
    return f"{c.name} ({c.region_id}, {c.country}): spawn score {c.score:.2f} = {parts}, {c.confidence} confidence"


async def call_tool(run: QlooRun, mem: Memory, tool: str, args: dict[str, Any]) -> str:
    try:
        if tool == "search_games":
            q = Query.model_validate(args)
            hits = await resolve.search_games(run, q.query, take=5)
            if not hits:
                raise ToolError(f"no Qloo video games match '{q.query}'; try the official title")
            # Search ranks cheap clones ("Truck Simulator 2023 - Driver Europe") next to the real game,
            # and popularity does not separate them: keep exact titles plus one other for disambiguation.
            exact = [h for h in hits if resolve.name_matches(q.query, h.name)]
            note = ""
            if exact:
                hits = exact + [h for h in hits if h not in exact][:1]
            else:
                note = "; no exact title match"
            lines = []
            for h in hits:
                existing = next((k for k, v in mem.games.items() if v[0] == h.entity_id), None)
                key = existing or mem.handle("g", mem.games)
                mem.games[key] = (h.entity_id, h.name)
                lines.append(f"{key} {h.name}" + (f" ({h.year})" if h.year else ""))
            return "Games: " + "; ".join(lines) + note

        if tool == "search_culture":
            q = Query.model_validate(args)
            hits = (await culture.search_culture(run, q.query, take=3))[:6]
            if not hits:
                raise ToolError(f"no Qloo films, shows or artists match '{q.query}'")
            lines = []
            for h in hits:
                existing = next((k for k, v in mem.culture.items() if v[0] == h.entity_id), None)
                key = existing or mem.handle("c", mem.culture)
                mem.culture[key] = (h.entity_id, h.name, h.type)
                lines.append(f"{key} {h.name} ({h.type.rsplit(':', 1)[-1].replace('_', ' ')})")
            return "Culture: " + "; ".join(lines)

        if tool == "find_place":
            q = Query.model_validate(args)
            places = (await scout.search_places(run, q.query))[:4]
            if not places:
                raise ToolError(f"no Qloo place matches '{q.query}'")
            lines = []
            for p in places:
                key = mem.handle("p", mem.places)
                label = ", ".join(x for x in (p.name, p.region) if x)
                mem.places[key] = (label, p.lat, p.lon)
                lines.append(f"{key} {label} ({p.lat:.2f}, {p.lon:.2f})")
            return "Places: " + "; ".join(lines)

        if tool == "rank_cities":
            a = RankArgs.model_validate(args)
            ids = mem.game_ids(a.games)
            cult = mem.culture_ids(a.culture)
            regions = city_ids(a.cities) if a.cities else DEFAULT_CITIES
            ranked, _ = await cities.score_cities(
                run, regions, await signal_for(run, mem, ids), list(a.platforms), cult
            )
            if not ranked:
                raise ToolError("no city could be scored")
            mem.ranking, mem.rank_args = ranked, a
            top = "\n".join(f"{i + 1}. {fmt_city(c)}" for i, c in enumerate(ranked[:8]))
            hidden = "; ".join(
                f"{h.name} #{h.rank} for this game, #{h.gamer_rank} for gamers overall"
                for h in cities.hidden_markets(ranked)
            )
            return f"Ranked {len(ranked)} cities (spawn score > 1 means over-indexing):\n{top}" + (
                f"\nHidden markets: {hidden}" if hidden else ""
            )

        if tool == "scout_place":
            pa = PlaceArgs.model_validate(args)
            if pa.place in mem.places:
                name, lat, lon = mem.places[pa.place]
            elif pa.place in cities.regions():
                r = cities.regions()[pa.place]
                name, lat, lon = r.name, r.lat, r.lon
            else:
                raise ToolError(f"unknown place '{pa.place}'; use a p handle or a city id")
            area = await scout.scout_area(run, lat, lon, 40)
            genres = ", ".join(f"{g.genre} x{g.lift:.2f}" for g in area.genres[:5])
            games = ", ".join(g.name for g in area.games[:5])
            m = area.mix
            return (
                f"{name}: genres vs all gamers: {genres}. Games locals love: {games}. "
                f"Platform taste match out of 100: PC {round(m.pc * 100)}, console "
                f"{round(m.console * 100)}, mobile {round(m.mobile * 100)}."
            )

        if tool == "audience":
            ga = GamesArgs.model_validate(args)
            aud = await demographics.audience(
                run, await signal_for(run, mem, mem.game_ids(ga.games))
            )
            age = max(aud.age, key=lambda b: b.index)
            gender = max(aud.gender, key=lambda g: g.index)
            ages = ", ".join(f"{b.band} {b.index * 100:+.1f}%" for b in aud.age)
            return f"Audience skew vs average: strongest age {age.band}; leans {gender.label} ({gender.index * 100:+.1f}%). Ages: {ages}."

        if tool == "find_partners":
            pt = PartnerArgs.model_validate(args)
            sig = await signal_for(run, mem, mem.game_ids(pt.games))
            names = {gid: n for gid, n in mem.games.values()}
            region = cities.regions()[city_ids([pt.city])[0]] if pt.city else None
            kinds: tuple[Any, ...] = (
                ("artist", "podcast", "movie") if region else partners.ALL_TYPES
            )
            out = []
            for kind in kinds:
                found = await partners.fetch_kind(run, kind, sig, names, region)
                out.append(
                    f"{kind}s: "
                    + ", ".join(
                        f"{p.name} (x{p.lift} vs all gamers)" if p.lift else p.name
                        for p in found[:3]
                    )
                )
            where = f" in {region.name}" if region else " worldwide"
            return f"Partners fans love{where}: " + "; ".join(out)
    except ValidationError as e:
        raise ToolError(f"bad args for {tool}: {e.errors()[0]['msg']}") from e
    raise ToolError(f"unknown tool {tool}")


def grounded(answer: str, mem: Memory, goal: str) -> list[str]:
    """Numbers and bold names in the answer must come from observations (or the user's goal)."""
    seen = "\n".join(mem.observations) + "\n" + goal
    allowed = {_to_float(n) for n in NUMBER.findall(seen)}
    problems = [
        f"number {n} not in any observation"
        for n in NUMBER.findall(answer)
        if _to_float(n) not in allowed
    ]
    low = seen.lower()
    bad_bold = {b.lower() for b in BOLD.findall(answer) if b.lower() not in low}
    problems += [
        f"name {b} not in any observation" for b in BOLD.findall(answer) if b.lower() in bad_bold
    ]
    # Places are the riskiest invention, so check known city names even when they are not bold.
    places = {r.name for r in scout.scout_points().values()} | set(EXTRA_CITIES)
    problems += [
        f"city {p} not in any observation"
        for p in sorted(places)
        if p.lower() not in low
        and p.lower() not in bad_bold
        and re.search(rf"\b{re.escape(p)}\b", answer, re.IGNORECASE)
    ]
    # A number must belong to the city it is written next to, not to another city in the ranking.
    lines = [x for o in mem.observations for x in re.split(r"\n|; ", o)]
    lines.append(" ".join(NUMBER.findall(goal)))  # the user's own numbers belong to no city
    seen_places = {p for p in places if p.lower() in low}  # unseen ones are rejected above
    problems += misattributed(answer, city_numbers(lines, seen_places), seen_places)
    return problems


def template_answer(mem: Memory) -> str:
    if not mem.ranking:
        return "The agent could not finish a city ranking, so it has no recommendation. Try a more specific goal."
    top = mem.ranking[:3]
    games = ", ".join(
        mem.games[h][1] for h in (mem.rank_args.games if mem.rank_args else []) if h in mem.games
    )
    cities_txt = "; ".join(
        f"**{c.name}** (spawn score {c.score:.2f}, {c.confidence} confidence)" for c in top
    )
    return (
        f"For players of {games or 'your comparable games'}, the strongest spawn points are {cities_txt}. "
        "The spawn score multiplies taste lift, platform fit and culture fit from Qloo heatmaps. "
        "It is an affinity index, not a sales forecast."
    )


def make_draft(mem: Memory, fin: FinishArgs | None, goal: str) -> PlanDraft | None:
    a = mem.rank_args
    if not a and not (fin and fin.games):
        return None
    game_h = [
        h
        for h in ((fin.games if fin and fin.games else None) or (a.games if a else []))
        if h in mem.games
    ]
    cult_h = [
        h
        for h in ((fin.culture if fin and fin.culture else None) or (a.culture if a else []))
        if h in mem.culture
    ]
    plats = (fin.platforms if fin and fin.platforms else None) or (
        list(a.platforms) if a else ALL_PLATFORMS
    )
    regions = [c for c in (fin.cities if fin else []) if c in cities.regions()]
    if len(regions) < 3:
        regions = [c.region_id for c in mem.ranking[:12]] or DEFAULT_CITIES
    return PlanDraft(
        title=(fin.title if fin else "") or "Your game",
        description=goal[:600],
        games=[DraftGame(entity_id=mem.games[h][0], name=mem.games[h][1]) for h in game_h[:5]],
        culture=[
            DraftCulture(
                entity_id=mem.culture[h][0], name=mem.culture[h][1], type=mem.culture[h][2]
            )
            for h in cult_h[:5]
        ],
        platforms=plats,
        regions=regions[:20],
    )


def history(steps: list[AgentStepOut]) -> str:
    if not steps:
        return "(none yet)"
    return "\n".join(
        f"Step {s.n}. thought: {s.thought}\n  tool: {s.tool} {json.dumps(s.args)}\n  observation: {s.observation}"
        for s in steps
    )


async def run_agent(
    run_id: str,
    goal: str,
    store: Store,
    qloo: QlooClient,
    llm: LLMProvider | None,
    *,
    timeout: float,
) -> AgentRun:
    async def emit(type_: str, data: dict[str, Any]) -> None:
        await store.add_event(run_id, type_, data)

    async def on_call(e: TraceEntry) -> None:
        await emit("qloo_call", {"cache_hit": e.cache_hit, "endpoint": e.endpoint})

    run = qloo.run(on_call, max_calls=MAX_QLOO_CALLS)
    mem = Memory()
    steps: list[AgentStepOut] = []
    result = AgentRun(id=run_id, status="running", goal=goal)

    def calls() -> Calls:
        es = run.trace.entries
        return Calls(live=sum(not e.cache_hit for e in es), cached=sum(e.cache_hit for e in es))

    async def end(answer: str, source: str, fin: FinishArgs | None, model: str | None) -> AgentRun:
        done = result.model_copy(
            update={
                "status": "done",
                "steps": steps,
                "answer": answer,
                "answer_source": source,
                "draft": make_draft(mem, fin, goal),
                "model": model,
                "calls": calls(),
            }
        )
        await emit("answer", {"answer": answer, "source": source})
        await store.finish_run(run_id, "done", done.model_dump(mode="json"))
        await emit("done", {"id": run_id})
        return done

    async def fail(code: str, message: str) -> AgentRun:
        failed = result.model_copy(
            update={
                "status": "failed",
                "steps": steps,
                "error": Problem(code=code, message=message),
                "calls": calls(),
            }
        )
        await store.finish_run(run_id, "failed", failed.model_dump(mode="json"))
        await emit("failed", {"code": code, "message": message})
        return failed

    if not qloo.configured:
        return await fail("qloo_unconfigured", "Set QLOO_API_KEY in apps/api/.env")
    if llm is None:
        return await fail("llm_unavailable", "No LLM provider is configured")

    budget = CallBudget(MAX_LLM_CALLS)
    model_name = f"{llm.name} · {llm.model}"
    all_ids = ", ".join(cities.regions())
    try:
        for n in range(1, MAX_STEPS + 1):
            prompt = render(
                "agent",
                goal=goal,
                default_cities=", ".join(DEFAULT_CITIES),
                all_cities=all_ids,
                history=history(steps),
            )
            try:
                step, _ = await complete_json(
                    llm, [{"role": "user", "content": prompt}], Step, budget, timeout=timeout
                )
            except LLMError as e:
                if mem.ranking:  # enough to answer from Qloo results alone
                    return await end(template_answer(mem), "template", None, None)
                return await fail(e.code, e.detail)
            await emit(
                "step", {"n": n, "thought": step.thought, "tool": step.tool, "args": step.args}
            )

            if step.tool == "finish":
                try:
                    fin = FinishArgs.model_validate(step.args)
                except ValidationError as e:
                    obs, ok = f"bad args for finish: {e.errors()[0]['msg']}", False
                else:
                    problems = grounded(fin.answer, mem, goal)
                    if not problems:
                        steps.append(
                            AgentStepOut(
                                n=n,
                                thought=step.thought,
                                tool="finish",
                                args=step.args,
                                observation="Answer accepted.",
                                ok=True,
                            )
                        )
                        await emit("observation", {"n": n, "text": "Answer accepted.", "ok": True})
                        return await end(fin.answer, "llm", fin, model_name)
                    obs, ok = (
                        "Answer rejected: "
                        + "; ".join(problems[:4])
                        + ". Use only observed names and numbers.",
                        False,
                    )
                    if n == MAX_STEPS:
                        return await end(template_answer(mem), "template", fin, None)
            else:
                try:
                    obs, ok = await call_tool(run, mem, step.tool, step.args), True
                    mem.observations.append(obs)
                except ToolError as e:
                    obs, ok = f"error: {e}", False
                except QlooError as e:
                    if type(e) is not QlooError and e.code not in (
                        "qloo_filter_ignored",
                        "qloo_bad_request",
                    ):
                        raise  # auth, budget, rate limit, unconfigured: fail closed
                    obs, ok = f"error: Qloo could not answer ({e.detail})", False
            obs = obs[:OBS_CHARS]
            steps.append(
                AgentStepOut(
                    n=n,
                    thought=step.thought,
                    tool=step.tool,
                    args=step.args,
                    observation=obs,
                    ok=ok,
                )
            )
            await emit("observation", {"n": n, "text": obs, "ok": ok})
        # Out of steps: answer from the Qloo ranking if there is one.
        return await end(template_answer(mem), "template", None, None)
    except AppError as e:
        return await fail(e.code, e.detail)
    except Exception:  # never leave a run stuck in "running"
        log.exception("agent run %s crashed", run_id)
        return await fail("internal_error", "Unexpected server error")
