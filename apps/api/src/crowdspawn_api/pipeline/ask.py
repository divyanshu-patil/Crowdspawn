"""Ask AI: an LLM answers a question from Qloo facts already on screen, checked like the brief.

Two subjects: a launch plan (facts carry result ids, so answers must cite them) and a scouted place
(no result ids, so names, numbers and cities are checked but citations are not required).
"""

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from ..grounding import NUMBER, _to_float, validate
from ..llm.base import LLMProvider, Message
from ..llm.structured import CallBudget, complete_json, render
from ..schemas import AskOut, AskScoutIn, BriefSection, Plan
from .brief import check, facts

NOT_IN_PLAN = "NOT_IN_PLAN"
NO_ANSWER = (
    "This plan's Qloo data doesn't answer that. Ask about its cities, audience, partners or budget."
)
NO_ANSWER_SCOUT = (
    "The Qloo data for this place doesn't answer that. Ask about its genres, platforms, local "
    "favourites or your game's verdict."
)
WITHHELD = "I couldn't answer that using only this Qloo data, so I won't guess."


class Answer(BaseModel):
    answer: str


def result_ids(v: Any) -> set[str]:
    """Every Qloo result id the plan carries: the only citations an answer may use."""
    if isinstance(v, dict):
        own = {v["result_id"]} if isinstance(v.get("result_id"), str) else set()
        return own | set(v.get("result_ids") or []) | {i for x in v.values() for i in result_ids(x)}
    if isinstance(v, list):
        return {i for x in v for i in result_ids(x)}
    return set()


async def _ask(
    llm: LLMProvider,
    prompt: str,
    errors_of: Callable[[str], list[str]],
    no_answer: str,
    timeout: float,
) -> AskOut:
    messages: list[Message] = [{"role": "user", "content": prompt}]
    budget = CallBudget(4)
    for _ in range(2):
        out, res = await complete_json(
            llm, messages, Answer, budget, max_tokens=400, timeout=timeout
        )
        text = out.answer.strip()
        if text == NOT_IN_PLAN:
            return AskOut(answer=no_answer, grounded=True, provider=res.provider, model=res.model)
        errors = errors_of(text)
        if not errors:
            return AskOut(answer=text, grounded=True, provider=res.provider, model=res.model)
        messages += [
            {"role": "assistant", "content": out.model_dump_json()},
            {
                "role": "user",
                "content": "The answer broke these rules: "
                + "; ".join(errors[:10])
                + f". Rewrite it using only the facts, or answer {NOT_IN_PLAN}.",
            },
        ]
    return AskOut(answer=WITHHELD, grounded=False, provider=res.provider, model=res.model)


async def answer(llm: LLMProvider, plan: Plan, question: str, timeout: float) -> AskOut:
    ids = result_ids(plan.model_dump())
    prompt = render(
        "ask", facts=json.dumps(facts(plan), ensure_ascii=False), question=question.strip()
    )
    return await _ask(
        llm,
        prompt,
        lambda text: check(plan, [BriefSection(heading="Answer", body=text)], ids),
        NO_ANSWER,
        timeout,
    )


def x(v: float) -> str:
    return f"{v:.2f}"


def scout_facts(body: AskScoutIn) -> dict[str, Any]:
    """The scout panel's numbers, formatted exactly as the panel shows them."""
    m = body.mix
    f: dict[str, Any] = {
        "place": body.place,
        "platform_taste_match_out_of_100": {
            "PC": round(m.pc * 100),
            "console": round(m.console * 100),
            "mobile": round(m.mobile * 100),
        },
        "genres_vs_all_gamers_here": [
            {"genre": g.genre, "lift": x(g.lift), "examples": g.examples} for g in body.genres
        ],
        "games_locals_love": body.games,
    }
    if j := body.judge:
        f["your_game_here"] = {
            "verdict": j.verdict,
            "verdict_bands": {b.verdict: x(b.min_score) for b in j.bands},
            "spawn_score": x(j.score),
            "taste_lift": x(j.lift),
            "platform_fit": x(j.platform_fit),
            **({"culture_fit": x(j.culture_fit)} if j.culture_fit is not None else {}),
            "confidence": j.confidence,
            "comparable_games": j.comps,
            "culture_anchors": j.culture,
            "against_world_cities": [
                {"place": "this spot" if r.here else r.name, "spawn_score": x(r.score)}
                for r in j.ranking
            ],
        }
    return f


def scout_errors(body: AskScoutIn, f: dict[str, Any], text: str) -> list[str]:
    j = body.judge
    here = {body.place, body.place.split(",")[0].strip()}  # "Mumbai, India" is also "Mumbai"
    places = here | ({r.name for r in j.ranking if not r.here} if j else set())
    names = {g.genre for g in body.genres} | {e for g in body.genres for e in g.examples}
    names |= set(body.games) | (
        set(j.comps) | set(j.culture) | {g.name for g in j.games} if j else set()
    )
    return validate(
        [BriefSection(heading="Answer", body=text)],
        trace_ids=set(),
        plan_cities=places,
        known_names=names,
        allowed_numbers={_to_float(n) for n in NUMBER.findall(json.dumps(f))},
        cite=False,
    )


async def answer_scout(llm: LLMProvider, body: AskScoutIn, timeout: float) -> AskOut:
    f = scout_facts(body)
    prompt = render(
        "ask_scout", facts=json.dumps(f, ensure_ascii=False), question=body.question.strip()
    )
    return await _ask(llm, prompt, lambda t: scout_errors(body, f, t), NO_ANSWER_SCOUT, timeout)
