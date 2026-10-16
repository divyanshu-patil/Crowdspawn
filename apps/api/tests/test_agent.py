"""Launch agent: tool loop, handle guard, grounded answers, caps and fail-closed (fake LLM and Qloo)."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from crowdspawn_api.llm.fake import FakeProvider
from crowdspawn_api.pipeline import agent, cities, partners, resolve
from crowdspawn_api.qloo.client import QlooClient
from crowdspawn_api.schemas import City, EntityOut, Partner
from crowdspawn_api.storage import Store

from .conftest import make_settings


def step(tool: str, args: dict[str, Any], thought: str = "next") -> str:
    return json.dumps({"thought": thought, "tool": tool, "args": args})


def city(rid: str, score: float) -> City:
    r = cities.regions()[rid]
    return City(
        region_id=rid, name=r.name, country=r.country, lat=r.lat, lon=r.lon, score=score, lift=score,
        platform_fit=1.0, target_score=0.8, baseline_score=0.8, cells=300, confidence="high",
        result_ids=["q1"],
    )  # fmt: skip


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def search_games(run: Any, q: str, take: int = 8) -> list[EntityOut]:
        return [EntityOut(entity_id=f"ID-{q}", name=q, type="urn:entity:videogame", year=2016)]

    async def expand_(run: Any, comps: Any) -> list[Any]:
        return []

    async def score(
        run: Any, regions: list[str], signal: list[str], platforms: Any, culture: Any
    ) -> Any:
        seen["score"] = (regions, signal, platforms, culture)
        return [city("tyo", 1.19), city("lon", 1.16), city("nyc", 0.95)], []

    async def fetch_kind(run: Any, kind: str, sig: Any, names: Any, region: Any) -> list[Partner]:
        return [
            Partner(entity_id=f"{kind}1", name=f"Top {kind}", affinity=0.9, why="-", result_id="q9")
        ]

    monkeypatch.setattr(resolve, "search_games", search_games)
    monkeypatch.setattr(agent.expand, "expand", expand_)
    monkeypatch.setattr(cities, "score_cities", score)
    monkeypatch.setattr(partners, "fetch_kind", fetch_kind)
    return seen


async def go(
    tmp_path: Path, replies: list[str], key: str = "test-key"
) -> tuple[Any, list[str], dict[str, Any] | None]:
    """Run the agent once; returns the result, its event types and the stored run row."""
    store = await Store.open(tmp_path / "a.sqlite3")
    qloo = QlooClient(make_settings(tmp_path, qloo_api_key=key), store)
    try:
        await store.create_run("a1", {"goal": "cozy farming game"})
        result = await agent.run_agent(
            "a1", "cozy farming game for PC", store, qloo, FakeProvider(replies), timeout=5
        )
        events = [t for _, t, _ in await store.events_after("a1", 0)]
        return result, events, await store.get_run("a1")
    finally:  # aiosqlite's worker thread would otherwise keep the test process alive
        await qloo.aclose()
        await store.close()


GOOD = [
    step("search_games", {"query": "Stardew Valley"}),
    step("search_games", {"query": "Animal Crossing"}),
    step("rank_cities", {"games": ["g1", "g2"], "platforms": ["pc"]}),
    step("find_partners", {"games": ["g1"], "city": "tyo"}),
    step(
        "finish",
        {
            "answer": "Launch first in **Tokyo** (spawn score 1.19), then **London** (1.16). Partner with **Top artist**.",
            "games": ["g1", "g2"],
            "cities": ["tyo", "lon", "nyc"],
            "title": "Moss Hollow",
        },
    ),
]


async def test_agent_plans_with_qloo_tools_and_hands_off_a_plan_draft(
    tmp_path: Path, tools: dict[str, Any]
) -> None:
    r, events, row = await go(tmp_path, GOOD)
    assert r.status == "done" and r.answer_source == "llm" and "**Tokyo**" in r.answer
    assert [s.tool for s in r.steps] == [
        "search_games",
        "search_games",
        "rank_cities",
        "find_partners",
        "finish",
    ]
    assert tools["score"][1] == ["ID-Stardew Valley", "ID-Animal Crossing"] and tools["score"][
        2
    ] == ["pc"]
    assert "1. Tokyo (tyo, JP): spawn score 1.19" in r.steps[2].observation
    assert r.draft and [g.entity_id for g in r.draft.games] == [
        "ID-Stardew Valley",
        "ID-Animal Crossing",
    ]
    assert r.draft.regions == ["tyo", "lon", "nyc"] and r.draft.title == "Moss Hollow"
    assert events[:2] == ["step", "observation"] and events[-2:] == ["answer", "done"]
    assert row and row["status"] == "done"


async def test_invented_handles_are_rejected_and_the_agent_recovers(
    tmp_path: Path, tools: dict[str, Any]
) -> None:
    replies = [step("rank_cities", {"games": ["g7"]}), *GOOD]
    r, _, _ = await go(tmp_path, replies)
    assert not r.steps[0].ok and "unknown game handles ['g7']" in r.steps[0].observation
    assert r.status == "done" and r.answer_source == "llm"


async def test_answer_with_invented_numbers_is_sent_back(
    tmp_path: Path, tools: dict[str, Any]
) -> None:
    bad = step(
        "finish", {"answer": "Launch in **Tokyo**; expect 50,000 sales and a 9.9 score there."}
    )
    ok = step(
        "finish",
        {"answer": "Launch first in **Tokyo** (spawn score 1.19), then **London** (1.16)."},
    )
    r, _, _ = await go(tmp_path, [*GOOD[:3], bad, ok])
    rejected = r.steps[3]
    assert not rejected.ok and "number 50,000 not in any observation" in rejected.observation
    assert r.answer_source == "llm" and "50,000" not in (r.answer or "")


async def test_out_of_steps_answers_from_the_qloo_ranking(
    tmp_path: Path, tools: dict[str, Any]
) -> None:
    rank = step("rank_cities", {"games": ["g1"]})
    loop = [GOOD[0], rank] + [step("search_games", {"query": "Stardew Valley"})] * 8
    r, _, _ = await go(tmp_path, loop)
    assert r.status == "done" and r.answer_source == "template" and len(r.steps) == agent.MAX_STEPS
    assert "**Tokyo** (spawn score 1.19, high confidence)" in (r.answer or "")
    assert r.draft and r.draft.regions[:2] == ["tyo", "lon"]


async def test_llm_failure_after_ranking_still_answers_from_qloo(
    tmp_path: Path, tools: dict[str, Any]
) -> None:
    rank = step("rank_cities", {"games": ["g1"]})
    r, _, _ = await go(tmp_path, [GOOD[0], rank, "not json", "still not json"])
    assert r.status == "done" and r.answer_source == "template"


async def test_llm_failure_before_any_qloo_result_fails(
    tmp_path: Path, tools: dict[str, Any]
) -> None:
    r, _, _ = await go(tmp_path, ["nope", "nope"])
    assert r.status == "failed" and r.error and r.error.code == "llm_unavailable"


async def test_fails_closed_without_qloo(tmp_path: Path, tools: dict[str, Any]) -> None:
    r, _, _ = await go(tmp_path, GOOD, key="")
    assert r.status == "failed" and r.error and r.error.code == "qloo_unconfigured" and not r.steps


def test_grounding_checks_numbers_and_bold_names() -> None:
    mem = agent.Memory(observations=["1. Tokyo (tyo, JP): spawn score 1.19"])
    assert agent.grounded("**Tokyo** at 1.19", mem, "goal") == []
    assert agent.grounded("**Osaka** at 1.19", mem, "goal") == ["name Osaka not in any observation"]
    assert agent.grounded("**Tokyo** at 2.5, budget $5,000", mem, "budget $5,000") == [
        "number 2.5 not in any observation"
    ]
    assert agent.grounded("Tokyo first, then Lagos.", mem, "goal") == [
        "city Lagos not in any observation"
    ]
    assert agent.grounded("Tokyo first, then Paris.", mem, "a story set in Paris") == []


def test_agent_route_runs_and_streams(client: TestClient, tools: dict[str, Any]) -> None:
    llm = client.app.state.deps.llm
    assert isinstance(llm, FakeProvider)
    llm.replies = list(GOOD)
    res = client.post("/v1/agent", json={"goal": "A cozy farming game for PC"})
    assert res.status_code == 202, res.text
    rid = res.json()["id"]
    run = client.get(f"/v1/agent/{rid}").json()
    assert run["status"] == "done" and run["draft"]["regions"] == ["tyo", "lon", "nyc"]
    with client.stream("GET", f"/v1/agent/{rid}/stream") as s:
        body = "".join(s.iter_text())
    assert "event: step" in body and "event: done" in body
    assert client.get("/v1/agent/nope").status_code == 404
    assert client.post("/v1/agent", json={"goal": "short"}).status_code == 422
