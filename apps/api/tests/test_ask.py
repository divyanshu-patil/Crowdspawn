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
