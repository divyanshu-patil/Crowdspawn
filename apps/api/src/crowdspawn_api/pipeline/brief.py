"""S8: the launch brief. The LLM writes prose over Qloo facts; a template is the grounded fallback."""

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from ..grounding import NUMBER, _to_float, validate
from ..llm.base import LLMError, LLMProvider
from ..llm.structured import CallBudget, complete_json, render
from ..schemas import Brief, BriefSection, Plan

log = logging.getLogger(__name__)


class BriefOut(BaseModel):
    sections: list[BriefSection] = Field(min_length=2, max_length=6)


def lift(x: float) -> str:
    return f"{x:.2f}"


def pct(x: float) -> str:
    return f"{x:.2f}%"


def usd(x: float) -> str:
    return f"${x:,.2f}"


def skew(x: float) -> str:
    return f"{x * 100:+.0f}%"


def facts(plan: Plan) -> dict[str, Any]:
    """Compact, pre-formatted Qloo facts. The LLM may copy these strings but never compute."""
    a = plan.audience
    return {
        "game": plan.input.game.title,
        "comps": [{"name": c.name, "result_id": c.result_id} for c in plan.comps],
        "similar_games": [{"name": g.name, "result_id": g.result_id} for g in plan.expanded[:8]],
        "cities": [
            {
                "name": c.name,
                "country": c.country,
                "lift": lift(c.lift),
                "confidence": c.confidence,
                "budget_share": pct(c.budget_share),
                **({"budget_usd": usd(c.budget_usd)} if c.budget_usd is not None else {}),
                "result_ids": c.result_ids,
            }
            for c in plan.cities
        ],
        "audience": {
            "age_skew": {b.band: skew(b.index) for b in a.age},
            "gender_skew": {g.label: skew(g.index) for g in a.gender},
            "result_id": a.result_id,
        }
        if a
        else None,
        "partners": {
            k: [
                {"name": p.name, "city": p.city, "result_id": p.result_id}
                for p in getattr(plan.partners, k)[:5]
            ]
            for k in ("artist", "podcast", "movie", "brand")
        },
        "budget_total": usd(plan.input.budget_usd) if plan.input.budget_usd else None,
    }


def _strip_ids(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _strip_ids(x) for k, x in v.items() if k not in ("result_id", "result_ids")}
    if isinstance(v, list):
        return [_strip_ids(x) for x in v]
    return v


def allowed_numbers(plan: Plan) -> set[float]:
    """Every number that appears in the facts, tokenised exactly like the validator does."""
    text = json.dumps(_strip_ids(facts(plan)))
    return {_to_float(n) for n in NUMBER.findall(text)}


def known_names(plan: Plan) -> set[str]:
    names = {plan.input.game.title} | {c.name for c in plan.comps} | {g.name for g in plan.expanded}
    for k in ("artist", "podcast", "movie", "brand"):
        names |= {p.name for p in getattr(plan.partners, k)}
    return names


def check(plan: Plan, sections: list[BriefSection], trace_ids: set[str]) -> list[str]:
    return validate(
        sections,
        trace_ids=trace_ids,
        plan_cities={c.name for c in plan.cities},
        known_names=known_names(plan),
        allowed_numbers=allowed_numbers(plan),
    )


def template_brief(plan: Plan) -> list[BriefSection]:
    top = plan.cities[:3]
    where = " ".join(
        f"**{c.name}** has an affinity lift of {lift(c.lift)} ({c.confidence} "
        f"confidence) [{c.result_ids[0]}]."
        for c in top
    )
    sections = [
        BriefSection(
            heading="Where to launch", body=f"Fans of games like yours over-index most in: {where}"
        )
    ]
    if plan.audience:
        a = plan.audience
        hi = max(a.age, key=lambda b: b.index)
        g = max(a.gender, key=lambda x: x.index)
        sections.append(
            BriefSection(
                heading="Who the players are",
                body=(
                    f"The strongest age skew is {hi.band} ({skew(hi.index)}), and the audience leans "
                    f"{g.label} ({skew(g.index)}) [{a.result_id}]."
                ),
            )
        )
    picks = [
        (k, getattr(plan.partners, k)[0])
        for k in ("artist", "podcast", "movie", "brand")
        if getattr(plan.partners, k)
    ]
    if picks:
        sections.append(
            BriefSection(
                heading="Who to partner with",
                body=" ".join(f"Top {k}: **{p.name}** [{p.result_id}]." for k, p in picks),
            )
        )
    funded = [c for c in plan.cities if c.budget_share > 0][:5]
    if funded:
        sections.append(
            BriefSection(
                heading="How to split the budget",
                body=" ".join(
                    f"**{c.name}**: {pct(c.budget_share)}"
                    + (f" ({usd(c.budget_usd)})" if c.budget_usd is not None else "")
                    + f" [{c.result_ids[0]}]."
                    for c in funded
                ),
            )
        )
    sections.append(
        BriefSection(
            heading="Caveats",
            body=(
                "This is an affinity index built from taste data, not a sales forecast. Treat it as a "
                "starting hypothesis and test it with small campaigns first."
            ),
        )
    )
    return sections


async def write_brief(
    plan: Plan,
    provider: LLMProvider | None,
    budget: CallBudget,
    trace_ids: set[str],
    *,
    max_tokens: int,
    timeout: float,
) -> Brief:
    def fallback(notice: str) -> Brief:
        return Brief(
            sections=template_brief(plan),
            source="template",
            provider=provider.name if provider else None,
            model=provider.model if provider else None,
            notice=notice,
        )

    if provider is None:
        return fallback("No LLM is configured, so this brief was generated from a template.")
    prompt = render("write_brief", facts=json.dumps(facts(plan), ensure_ascii=False))
    messages: list[Any] = [
        {"role": "system", "content": "You are a precise launch strategist."},
        {"role": "user", "content": prompt},
    ]
    try:
        for attempt in range(2):
            out, result = await complete_json(
                provider, messages, BriefOut, budget, max_tokens=max_tokens, timeout=timeout
            )
            errors = check(plan, out.sections, trace_ids)
            if not errors:
                return Brief(
                    sections=out.sections,
                    source="llm",
                    provider=result.provider,
                    model=result.model,
                )
            log.info("brief failed grounding (attempt %d): %s", attempt + 1, errors[:5])
            messages = [
                *messages,
                {"role": "assistant", "content": out.model_dump_json()},
                {
                    "role": "user",
                    "content": "The brief broke these rules: "
                    + "; ".join(errors[:10])
                    + ". Rewrite it using only the facts.",
                },
            ]
        return fallback(
            "The LLM brief cited facts that are not in the Qloo results, "
            "so a grounded template is shown instead."
        )
    except LLMError as e:
        log.warning("brief LLM failed: %s", e.detail)
        return fallback("The LLM was unavailable, so this brief was generated from a template.")
