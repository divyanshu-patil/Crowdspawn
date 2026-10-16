"""Pure-function and Phase 0 fixture tests: spawn score, confidence, budget, matching, grounding."""

import json
from pathlib import Path

import pytest

from crowdspawn_api.grounding import validate
from crowdspawn_api.pipeline.brief import check, template_brief
from crowdspawn_api.pipeline.budget import largest_remainder, split_budget
from crowdspawn_api.pipeline.cities import regions
from crowdspawn_api.pipeline.confidence import confidence
from crowdspawn_api.pipeline.resolve import name_matches
from crowdspawn_api.pipeline.scoring import CityMetrics, spawn_scores
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
        score=lift,
        lift=lift,
        platform_fit=1.0,
        target_score=0.8,
        baseline_score=0.8 / lift,
        cells=200,
        confidence=conf,  # type: ignore[arg-type]
        result_ids=["q1", "q2"],
    )


def panels(pc: float, mobile: float, console: float) -> dict[str, float]:
    return {"pc": pc, "mobile": mobile, "console": console}


def test_lift_order_differs_from_raw_order() -> None:
    # Raw comp-fan scores say New York > Tokyo; against each city's all-gamer baseline Tokyo wins.
    m = {
        "nyc": CityMetrics(target=0.80, panels=panels(0.8, 0.8, 0.8), cells=300),
        "tyo": CityMetrics(target=0.75, panels=panels(0.45, 0.45, 0.45), cells=300),
    }
    s = spawn_scores(m, [])
    assert max(m, key=lambda k: m[k].target) == "nyc"
    assert max(s, key=lambda k: s[k].score) == "tyo"
    assert s["tyo"].lift == pytest.approx(1.667, abs=1e-3)
    assert s["tyo"].platform_fit == 1.0 and s["tyo"].culture_fit is None


def test_platform_fit_moves_console_games_away_from_console_light_markets() -> None:
    m = {
        "ist": CityMetrics(target=0.9, panels=panels(0.95, 0.95, 0.6), cells=300),
        "mex": CityMetrics(target=0.9, panels=panels(0.85, 0.85, 0.95), cells=300),
    }
    assert spawn_scores(m, ["pc", "mobile", "console"])["ist"].platform_fit == pytest.approx(1.0)
    console = spawn_scores(m, ["console"])
    assert console["mex"].score > console["ist"].score
    pc = spawn_scores(m, ["pc"])
    assert pc["ist"].score > pc["mex"].score


def test_culture_fit_lifts_the_settings_home_market() -> None:
    # Delhi Gullies: equal taste lift, but fans of Indian films and music are concentrated in Delhi.
    m = {
        "del": CityMetrics(target=0.92, panels=panels(0.94, 0.95, 0.75), cells=900, culture=0.82),
        "lon": CityMetrics(target=0.83, panels=panels(0.69, 0.81, 0.84), cells=900, culture=0.40),
        "nyc": CityMetrics(target=0.85, panels=panels(0.76, 0.84, 0.94), cells=900, culture=0.30),
    }
    taste_only = spawn_scores(
        {k: CityMetrics(v.target, v.panels, v.cells) for k, v in m.items()}, []
    )
    assert max(taste_only, key=lambda k: taste_only[k].score) == "lon"
    s = spawn_scores(m, [])
    assert max(s, key=lambda k: s[k].score) == "del"
    ratios = [s[k].culture_fit for k in m]
    assert sum(r for r in ratios if r is not None) / 3 == pytest.approx(1.0)


def test_phase0_comp_sets_rank_cities_differently() -> None:
    report = json.loads((FIXTURES / "spike" / "report.json").read_text())
    rho = report["report"]["heatmap"]["spearman_cozy_vs_rogue_lift"]
    assert rho < 0.9
    assert report["report"]["heatmap"]["cozy_top5"] != report["report"]["heatmap"]["rogue_top5"]


@pytest.mark.parametrize(
    ("score", "cells", "expected"),
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
def test_confidence_boundaries(score: float, cells: int, expected: str) -> None:
    assert confidence(score, cells) == expected


def test_budget_shares_sum_to_100_with_and_without_budget() -> None:
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
    ids = {"q1", "q2", "q21", "q27"} | {i for c in plan.cities for i in c.result_ids}
    return check(plan, [BriefSection(heading="Where", body=body)], ids)


def test_grounding_accepts_facts() -> None:
    plan = sample_plan()
    top = plan.cities[0]
    body = f"**{top.name}** has spawn score {top.score:.2f}, lift {top.lift:.2f} [{top.result_ids[0]}]."
    assert ground(plan, body) == []


def test_grounding_rejects_invented_city() -> None:
    plan = sample_plan()
    errors = ground(plan, "Launch in **Melbourne** first [q1].")
    assert any("Melbourne" in e for e in errors)
    errors = ground(plan, "Fans cluster in Melbourne [q1].")  # not bolded, still caught
    assert any("melbourne" in e for e in errors)


def test_grounding_rejects_invented_number_and_missing_citation() -> None:
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


class StubRun:
    """Replays one recorded body for any call (enough for single-call helpers)."""

    def __init__(self, body: object):
        self.body = body
        self.params: list[dict[str, str]] = []

    async def get(self, step: str, path: str, params: dict[str, str]) -> tuple[str, object]:
        self.params.append(params)
        return "q2", self.body


async def test_culture_lookup_keeps_films_shows_artists_and_drops_unknown_ids() -> None:
    from crowdspawn_api.pipeline.culture import lookup_culture

    rec = json.loads((FIXTURES / "entities" / "culture_india.json").read_text())
    ids = rec["request"]["params"]["entity_ids"].split(",") + ["NOT-A-REAL-ID"]
    anchors, missing = await lookup_culture(StubRun(rec["body"]), ids)  # type: ignore[arg-type]
    assert [a.name for a in anchors] == ["Gully Boy", "3 Idiots", "Arijit Singh", "Sacred Games"]
    assert {a.type for a in anchors} == {
        "urn:entity:movie",
        "urn:entity:artist",
        "urn:entity:tv_show",
    }
    assert missing == ["NOT-A-REAL-ID"] and all(a.result_id == "q2" for a in anchors)
    assert await lookup_culture(StubRun({}), []) == ([], [])  # type: ignore[arg-type]
