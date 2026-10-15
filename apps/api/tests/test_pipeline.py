"""Pure-function and Phase 0 fixture tests: lift, confidence, budget, matching, grounding."""

import json
from pathlib import Path

import pytest

from crowdspawn_api.grounding import validate
from crowdspawn_api.pipeline.brief import check, template_brief
from crowdspawn_api.pipeline.budget import largest_remainder, split_budget
from crowdspawn_api.pipeline.cities import make_city, regions
from crowdspawn_api.pipeline.confidence import confidence
from crowdspawn_api.pipeline.resolve import name_matches
from crowdspawn_api.schemas import BriefSection, City, Plan

from .conftest import FIXTURES, PLAN_INPUT


def city(rid: str, lift: float, conf: str = "high") -> City:
    r = regions()[rid]
    return City(
        region_id=rid,
        name=r.name,
        country=r.country,
        lat=r.lat,
        lon=r.lon,
        lift=lift,
        target_score=0.8,
        baseline_score=0.8 / lift,
        cells=200,
        confidence=conf,  # type: ignore[arg-type]
        result_ids=["q1", "q2"],
    )


def test_lift_order_differs_from_raw_order() -> None:  # Q5
    # Raw scores say New York > Tokyo; against each city's baseline Tokyo over-indexes far more.
    nyc = make_city(regions()["nyc"], ("q1", 0.80, 300), ("q2", 0.80, 300))
    tyo = make_city(regions()["tyo"], ("q3", 0.75, 300), ("q4", 0.45, 300))
    raw = sorted([nyc, tyo], key=lambda c: -c.target_score)
    by_lift = sorted([nyc, tyo], key=lambda c: -c.lift)
    assert [c.name for c in raw] == ["New York", "Tokyo"]
    assert [c.name for c in by_lift] == ["Tokyo", "New York"]
    assert tyo.lift == pytest.approx(1.667, abs=1e-3)


def test_phase0_comp_sets_rank_cities_differently() -> None:  # Q6
    report = json.loads((FIXTURES / "spike" / "report.json").read_text())
    rho = report["report"]["heatmap"]["spearman_cozy_vs_rogue_lift"]
    assert rho < 0.9
    assert report["report"]["heatmap"]["cozy_top5"] != report["report"]["heatmap"]["rogue_top5"]


@pytest.mark.parametrize(
    ("lift", "cells", "expected"),
    [
        (1.10, 150, "high"),
        (1.0999, 150, "medium"),
        (1.10, 149, "medium"),
        (0.90, 150, "high"),
        (1.03, 50, "medium"),
        (1.0299, 50, "low"),
        (1.03, 49, "low"),
        (1.5, 10, "low"),
    ],
)
def test_confidence_boundaries(lift: float, cells: int, expected: str) -> None:  # P8
    assert confidence(lift, cells) == expected


def test_budget_shares_sum_to_100_with_and_without_budget() -> None:  # P7
    cities = [
        city("tyo", 1.7),
        city("sfo", 1.19, "medium"),
        city("sel", 1.13, "low"),
        city("nyc", 0.99, "low"),
    ]
    for budget in (None, 5000.0, 333.33, 1.0):
        out = split_budget(cities, budget)
        assert sum(round(c.budget_share * 100) for c in out) == 10_000
        assert out[-1].budget_share == 0  # under-indexing city gets nothing
        if budget:
            assert round(sum(c.budget_usd or 0 for c in out) * 100) == round(budget * 100)
        else:
            assert all(c.budget_usd is None for c in out)


def test_budget_when_no_city_over_indexes() -> None:
    out = split_budget([city("nyc", 0.9), city("lon", 0.95)], 100)
    assert sum(c.budget_share for c in out) == pytest.approx(100)


def test_largest_remainder_rounding() -> None:
    assert sum(largest_remainder([1, 1, 1], 100)) == 100
    assert largest_remainder([0, 0], 10) == [5, 5]


@pytest.mark.parametrize(
    ("query", "candidate", "ok"),
    [
        ("hades 2", "Hades II", True),
        ("Hollow Knight Silksong", "Hollow Knight: Silksong", True),
        ("the witness", "The Witness", True),
        ("Hades", "Hades II", False),
        ("Peak", "Peaky Blinders", False),
        ("Dispatch", "The Dispatcher", False),
        ("Stardew Valley", "Minecraft", False),
    ],
)
def test_name_matching(query: str, candidate: str, ok: bool) -> None:
    assert name_matches(query, candidate) is ok


def sample_plan() -> Plan:
    sample = Path(__file__).parents[3] / "apps" / "web" / "public" / "sample-plan.json"
    return Plan.model_validate(json.loads(sample.read_text()))


def ground(plan: Plan, body: str) -> list[str]:
    return check(plan, [BriefSection(heading="Where", body=body)], {"q1", "q2", "q21", "q27"})


def test_grounding_accepts_facts() -> None:
    plan = sample_plan()
    top = plan.cities[0]
    assert ground(plan, f"**{top.name}** has lift {top.lift:.2f} [{top.result_ids[0]}].") == []


def test_grounding_rejects_invented_city() -> None:  # L7
    plan = sample_plan()
    errors = ground(plan, "Launch in **Melbourne** first [q1].")
    assert any("Melbourne" in e for e in errors)
    errors = ground(plan, "Fans cluster in Melbourne [q1].")  # not bolded, still caught
    assert any("melbourne" in e for e in errors)


def test_grounding_rejects_invented_number_and_missing_citation() -> None:  # L7
    plan = sample_plan()
    top = plan.cities[0].name
    assert any("37%" in e for e in ground(plan, f"**{top}** gets 37% of players [q1]."))
    assert any("citation" in e for e in ground(plan, f"**{top}** leads the ranking."))
    assert any("[q999]" in e for e in ground(plan, f"**{top}** leads [q999]."))


def test_template_brief_is_grounded() -> None:
    plan = sample_plan()
    ids = {i for c in plan.cities for i in c.result_ids} | {plan.audience.result_id}  # type: ignore[union-attr]
    ids |= {
        p.result_id
        for k in ("artist", "podcast", "movie", "brand")
        for p in getattr(plan.partners, k)
    }
    assert check(plan, template_brief(plan), ids) == []


def test_validate_small_counts_allowed() -> None:
    errors = validate(
        [BriefSection(heading="Top 3", body="The top 3 cities matter.")],
        trace_ids=set(),
        plan_cities=set(),
        known_names=set(),
        allowed_numbers=set(),
    )
    assert errors == []


def test_plan_input_fixture_shape() -> None:
    assert 1 <= len(PLAN_INPUT["comp_entity_ids"]) <= 5
