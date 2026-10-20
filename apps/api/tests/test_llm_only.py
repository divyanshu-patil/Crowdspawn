import json
from pathlib import Path
from typing import Any

from crowdspawn_api.llm.fake import FakeProvider
from crowdspawn_api.pipeline import llm_only
from crowdspawn_api.pipeline.partners import GAMERS
from crowdspawn_api.schemas import Plan

SAMPLE = Path(__file__).parents[3] / "apps" / "web" / "public" / "sample-plan.json"


class StubRun:
    """Qloo search knows two of the LLM's names; insights give comp fans 1.2x the all-gamers affinity."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def get(
        self, step: str, path: str, params: dict[str, str], ttl: float | None = None
    ) -> tuple[str, Any]:
        self.calls.append((path, params))
        if path == "/search":
            name = params["query"]
            hits = (
                []
                if "Made Up" in name
                else [{"name": name, "entity_id": f"id-{name}", "types": [params["types"]]}]
            )
            return "q1", {"results": hits}
        aff = 0.6 if params["signal.interests.entities"] == GAMERS else 0.72
        ids = params["filter.entities"].split(",")
        entities = [{"name": i, "entity_id": i, "query": {"affinity": aff}} for i in ids]
        return "q9", {"results": {"entities": entities}}


async def test_llm_only_checks_every_name_in_qloo_and_scores_it_like_the_plan() -> None:
    plan = Plan.model_validate(json.loads(SAMPLE.read_text()))
    reply = {
        "cities": ["not-a-city", plan.cities[-1].region_id],
        "artist": ["Real Artist", "Made Up Band"],
        "podcast": ["Real Podcast"],
        "movie": [],
        "brand": ["Real Brand", "Real Brand"],
    }
    run = StubRun()
    out = await llm_only.compare(FakeProvider([json.dumps(reply)]), run, plan, 5)  # type: ignore[arg-type]

    assert out.cities[0] == plan.cities[-1].region_id  # unknown ids dropped
    assert sorted(out.cities) == sorted(c.region_id for c in plan.cities)  # every candidate kept
    by = {k.kind: k for k in out.partners}
    assert [p.name for p in by["artist"].picks] == ["Real Artist", "Made Up Band"]
    assert by["artist"].found == 1 and by["artist"].picks[1].entity_id is None  # never scored
    assert by["artist"].picks[0].lift == 1.2 and by["artist"].median_lift == 1.2
    assert by["brand"].found == 1  # duplicates collapse
    assert by["movie"].picks == [] and by["movie"].median_lift is None
    assert by["artist"].qloo_median_lift is not None  # the plan's own list, same scale
    assert len(run.calls) <= llm_only.QLOO_CALLS


async def test_llm_only_prompt_does_not_leak_qloos_city_order() -> None:
    plan = Plan.model_validate(json.loads(SAMPLE.read_text()))
    reply = {"cities": [], "artist": [], "podcast": [], "movie": [], "brand": []}
    llm = FakeProvider([json.dumps(reply)])
    await llm_only.compare(llm, StubRun(), plan, 5)  # type: ignore[arg-type]
    prompt = llm.calls[0][0]["content"]
    listed = [c.name for c in plan.cities]
    positions = [prompt.index(f"({n})") for n in sorted(listed)]
    assert positions == sorted(positions)  # alphabetical, not ranked
    assert [c.name for c in plan.cities] != sorted(
        listed
    )  # the sample's ranking differs, so this bites
