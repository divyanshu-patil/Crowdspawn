"""Scout judge: LLM names -> Qloo scoring -> verdict with probability (fakes for Qloo and the LLM)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from crowdspawn_api.llm.fake import FakeProvider
from crowdspawn_api.pipeline import cities, culture, expand, judge, resolve, scout
from crowdspawn_api.schemas import Comp, EntityOut, LocalGame, Region, Suggestion
from crowdspawn_api.settings import PLATFORM_PANELS

PANEL_IDS = {ids[0] for ids in PLATFORM_PANELS.values()}


@pytest.mark.parametrize(
    ("score", "conf", "p"),
    [
        (1.0, "high", 0.5),
        (1.10, "high", 0.767),
        (1.10, "low", 0.633),
        (5.0, "high", 0.97),
        (0.2, "high", 0.03),
    ],
)
def test_probability_is_capped_and_shrinks_with_weak_evidence(
    score: float, conf: str, p: float
) -> None:
    assert judge.probability(score, conf) == pytest.approx(p, abs=1e-3)


def test_tiers_and_number_check() -> None:
    assert [judge.tier(x) for x in (0.9, 0.8, 0.6, 0.5, 0.2)] == [
        "Superb",
        "Excellent",
        "Yes",
        "Maybe",
        "No",
    ]
    facts = {"probability": "77%", "spawn score": "1.10"}
    assert judge.numbers_ok("Yes, 77% and 1.10.", facts)
    assert not judge.numbers_ok("Yes, 90% likely.", facts)


@pytest.fixture
def fake_qloo_judge(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Here (Delhi) over-indexes on taste and culture; reference cities do not."""
    seen: dict[str, Any] = {"heat": 0}

    async def heat(run: Any, r: Region, ids: Any, ttl: Any = None) -> tuple[str, float, int]:
        seen["heat"] += 1
        here = abs(r.lat - 28.6) < 0.5
        first = list(ids)[0]
        if first in PANEL_IDS:
            return "q", 0.8, 300
        if first == "CULT":
            return "q", 0.9 if here else 0.3, 300
        return "q", 0.92 if here else 0.8, 300

    async def names(run: Any, ns: list[str]) -> tuple[list[Suggestion], list[str]]:
        hit = EntityOut(entity_id="G1", name="Grand Theft Auto V", type="urn:entity:videogame")
        return [Suggestion(input_name=ns[0], resolved=hit)], ns[1:]

    async def anchors(run: Any, pairs: Any) -> tuple[list[EntityOut], list[str]]:
        return [EntityOut(entity_id="CULT", name="Gully Boy", type="urn:entity:movie")], []

    async def none(*a: Any, **k: Any) -> list[Any]:
        return []

    async def games(run: Any, r: Region) -> list[LocalGame]:
        return [LocalGame(entity_id="P", name="PUBG", affinity=0.99)]

    for mod in (scout, cities):
        monkeypatch.setattr(mod, "heatmap_score", heat)
    monkeypatch.setattr(resolve, "resolve_names", names)
    monkeypatch.setattr(culture, "resolve_culture", anchors)
    monkeypatch.setattr(expand, "expand", none)
    monkeypatch.setattr(scout, "local_games", games)
    return seen


BODY = {
    "lat": 28.61,
    "lon": 77.21,
    "title": "Delhi Gullies",
    "description": "GTA-style crime game in Delhi",
    "platforms": ["pc"],
}


def test_judge_scores_here_against_reference_cities(
    client: TestClient, fake_qloo_judge: dict[str, Any]
) -> None:
    r = client.post("/v1/scout/judge", json=BODY)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["comps"] == ["Grand Theft Auto V"] and d["culture"] == ["Gully Boy"]
    assert (
        "Not A Real Game 9000" in d["dropped"]
    )  # the fake LLM's made-up name never reaches scoring
    assert d["lift"] == pytest.approx(1.15) and d["platform_fit"] == pytest.approx(1.0)
    assert d["culture_fit"] > 2  # 0.9 here vs 0.3 elsewhere, normalised over all places
    assert (
        d["ranking"][0]["here"] and len(d["ranking"]) == 8
    )  # Delhi itself is not its own reference
    assert d["verdict"] == "Superb" and d["probability"] == 0.97
    assert d["summary_source"] == "llm" and d["summary"].startswith("Superb with 97%")


def test_judge_summary_with_invented_numbers_falls_back_to_template(
    client: TestClient, fake_qloo_judge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = client.app.state.deps.llm
    assert isinstance(llm, FakeProvider)
    replies = [
        '{"names": ["GTA V"]}',
        '{"anchors": []}',
        '{"summary": "Superb: sells 2,000,000 copies here for sure."}',
    ]
    llm.replies = replies
    d = client.post("/v1/scout/judge", json=BODY).json()
    assert d["summary_source"] == "template" and "not a sales forecast" in d["summary"]
    assert d["culture"] == [] and d["culture_fit"] is None


def test_judge_needs_a_resolvable_comp(
    client: TestClient, fake_qloo_judge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nothing(run: Any, ns: list[str]) -> tuple[list[Suggestion], list[str]]:
        return [], ns

    monkeypatch.setattr(resolve, "resolve_names", nothing)
    r = client.post("/v1/scout/judge", json=BODY)
    assert r.status_code == 422 and r.json()["code"] == "comp_unresolved"


def test_judge_validates_input(client: TestClient) -> None:
    assert client.post("/v1/scout/judge", json={**BODY, "description": "short"}).status_code == 422
    client.app.state.deps.llm = None
    assert client.post("/v1/scout/judge", json=BODY).json()["code"] == "llm_unavailable"


def test_user_picked_comps_are_kept_first(
    client: TestClient, fake_qloo_judge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def lookup(run: Any, ids: list[str]) -> tuple[list[Comp], list[str]]:
        return [Comp(entity_id="S1", name="Sleeping Dogs", result_id="q1")], []

    monkeypatch.setattr(resolve, "lookup_comps", lookup)
    d = client.post("/v1/scout/judge", json={**BODY, "comp_entity_ids": ["S1"]}).json()
    assert d["comps"] == ["Sleeping Dogs", "Grand Theft Auto V"]
