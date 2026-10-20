"""Scout judge: LLM names -> Qloo scoring -> verdict from score bands (fakes for Qloo and the LLM)."""

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from crowdspawn_api.llm.fake import FakeProvider
from crowdspawn_api.pipeline import cities, culture, expand, judge, resolve, scout
from crowdspawn_api.schemas import Comp, EntityOut, LocalGame, Region, Suggestion
from crowdspawn_api.settings import PLATFORM_PANELS

PANEL_IDS = {ids[0] for ids in PLATFORM_PANELS.values()}


def old_verdict(score: float, conf: str) -> str:
    """The retired probability verdict (logistic, never calibrated), kept only to check the bands."""
    p = 1 / (1 + math.exp(-math.log(score) / 0.08))
    p = 0.5 + (p - 0.5) * {"high": 1.0, "medium": 0.75, "low": 0.5}[conf]
    p = min(0.97, max(0.03, p))
    cuts = ((0.85, "Legendary"), (0.72, "Epic"), (0.58, "Rare"), (0.42, "Uncommon"))
    return next((w for c, w in cuts if p >= c), "Common")


@pytest.mark.parametrize("conf", ["high", "medium", "low"])
def test_score_bands_reproduce_the_old_verdicts(conf: str) -> None:
    """J4: same words as before, from the spawn score alone (3-decimal scores, 0.500 to 2.000)."""
    for i in range(500, 2001):
        score = i / 1000
        assert judge.tier(score, conf) == old_verdict(score, conf), (score, conf)
    assert judge.bands(conf)[0].min_score > 1


def test_tiers_and_number_check() -> None:
    assert [judge.tier(x, "high") for x in (1.2, 1.1, 1.03, 1.0, 0.9)] == [
        "Legendary",
        "Epic",
        "Rare",
        "Uncommon",
        "Common",
    ]
    assert judge.tier(5.0, "low") == "Epic"  # weak evidence never reaches Legendary
    facts = {"spawn score": "1.10", "taste lift": "1.05"}
    assert judge.numbers_ok("Yes, 1.10 from 1.05.", facts)
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
    assert d["verdict"] == "Legendary" and "probability" not in d
    assert [b["verdict"] for b in d["bands"]] == ["Legendary", "Epic", "Rare", "Uncommon"]
    assert d["summary_source"] == "llm" and d["summary"].startswith("Legendary with spawn score")


def test_judge_summary_with_invented_numbers_falls_back_to_template(
    client: TestClient, fake_qloo_judge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = client.app.state.deps.llm
    assert isinstance(llm, FakeProvider)
    replies = [
        '{"names": ["GTA V"]}',
        '{"anchors": []}',
        '{"summary": "Legendary: sells 2,000,000 copies here for sure."}',
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
