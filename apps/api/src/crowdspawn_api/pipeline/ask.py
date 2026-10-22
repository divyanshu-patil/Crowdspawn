"""Ask the plan: an LLM answers a question from the plan's Qloo facts only, checked like the brief."""

import json
from typing import Any

from pydantic import BaseModel

from ..llm.base import LLMProvider, Message
from ..llm.structured import CallBudget, complete_json, render
from ..schemas import AskOut, BriefSection, Plan
from .brief import check, facts

NOT_IN_PLAN = "NOT_IN_PLAN"
NO_ANSWER = (
    "This plan's Qloo data doesn't answer that. Ask about its cities, audience, partners or budget."
)
WITHHELD = "I couldn't answer that using only this plan's Qloo data, so I won't guess."


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


async def answer(llm: LLMProvider, plan: Plan, question: str, timeout: float) -> AskOut:
    ids = result_ids(plan.model_dump())
    prompt = render(
        "ask", facts=json.dumps(facts(plan), ensure_ascii=False), question=question.strip()
    )
    messages: list[Message] = [{"role": "user", "content": prompt}]
    budget = CallBudget(4)
    for _ in range(2):
        out, res = await complete_json(
            llm, messages, Answer, budget, max_tokens=400, timeout=timeout
        )
        text = out.answer.strip()
        if text == NOT_IN_PLAN:
            return AskOut(answer=NO_ANSWER, grounded=True, provider=res.provider, model=res.model)
        errors = check(plan, [BriefSection(heading="Answer", body=text)], ids)
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
