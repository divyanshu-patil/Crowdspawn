import json
from pathlib import Path

from fastapi.testclient import TestClient

from crowdspawn_api.llm.fake import FakeProvider
from crowdspawn_api.pipeline.ask import NO_ANSWER, WITHHELD

SAMPLE = json.loads((Path(__file__).parents[2] / "web" / "public" / "sample-plan.json").read_text())


def ask(client: TestClient, fake: FakeProvider, q: str = "Where first?") -> dict:  # type: ignore[type-arg]
    client.app.state.deps.llm = fake  # type: ignore[attr-defined]
    r = client.post("/v1/ask", json={"plan": SAMPLE, "question": q})
    assert r.status_code == 200, r.text
    out: dict = r.json()  # type: ignore[type-arg]
    return out


def test_ask_answers_from_plan_facts(client: TestClient) -> None:
    out = ask(client, FakeProvider())
    top = SAMPLE["cities"][0]
    assert out["grounded"] and f"**{top['name']}**" in out["answer"]


def test_ask_withholds_an_answer_that_leaves_the_data(client: TestClient) -> None:
    bad = json.dumps({"answer": "Launch in **Melbourne** first, 37% of players [q999]."})
    out = ask(client, FakeProvider(replies=[bad, bad]))
    assert out == {**out, "answer": WITHHELD, "grounded": False}


def test_ask_says_when_the_plan_has_no_answer(client: TestClient) -> None:
    out = ask(client, FakeProvider(replies=[json.dumps({"answer": "NOT_IN_PLAN"})]), "Weather?")
    assert out["answer"] == NO_ANSWER


AREA = {
    "place": "Mumbai, India",
    "mix": {"pc": 0.71, "mobile": 0.83, "console": 0.64, "general": 0.73},
    "genres": [{"genre": "Racing", "lift": 1.18, "examples": ["Forza Horizon 5"]}],
    "games": ["BGMI", "Free Fire"],
}


def ask_scout(client: TestClient, fake: FakeProvider, q: str = "What works here?") -> dict:  # type: ignore[type-arg]
    client.app.state.deps.llm = fake  # type: ignore[attr-defined]
    r = client.post("/v1/scout/ask", json={**AREA, "question": q})
    assert r.status_code == 200, r.text
    out: dict = r.json()  # type: ignore[type-arg]
    return out


def test_scout_ask_answers_from_the_area_without_citations(client: TestClient) -> None:
    out = ask_scout(client, FakeProvider())
    assert out["grounded"] and "**Mumbai, India**" in out["answer"] and "1.18" in out["answer"]
    short = json.dumps(
        {"answer": "Racing fans show up most in **Mumbai** (x1.18), and mobile scores 83."}
    )
    assert ask_scout(client, FakeProvider(replies=[short]))["grounded"]


def test_scout_ask_withholds_invented_numbers_and_places(client: TestClient) -> None:
    for bad in (
        "**Mumbai** has 3 million gamers.",
        "Try **Melbourne** instead.",
        "**Mumbai** is 47% mobile.",
    ):
        reply = json.dumps({"answer": bad})
        out = ask_scout(client, FakeProvider(replies=[reply, reply]))
        assert out["answer"] == WITHHELD, bad
