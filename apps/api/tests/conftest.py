import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from crowdspawn_api.main import create_app
from crowdspawn_api.routes import v1
from crowdspawn_api.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "qloo"
PLAN_DIR = FIXTURES / "plan_roguelike"
QLOO = "https://hackathon.api.qloo.com"
TEST_KEY = "test-qloo-key-never-leaks"


def load_recorded(directory: Path = PLAN_DIR) -> dict[tuple[str, tuple[tuple[str, str], ...]], Any]:
    """Map (path, sorted params) -> recorded body for every fixture in a directory."""
    out = {}
    for f in directory.glob("q*.json"):
        d = json.loads(f.read_text())
        out[(d["request"]["path"], tuple(sorted(d["request"]["params"].items())))] = d["body"]
    return out


RECORDED = load_recorded()
PLAN_INPUT = json.loads((PLAN_DIR / "_plan_input.json").read_text())


class FakeQloo:
    """respx side effect that replays recorded Qloo responses and counts calls."""

    def __init__(self, recorded: dict[Any, Any] | None = None):
        self.recorded = recorded if recorded is not None else RECORDED
        self.requests: list[httpx.Request] = []
        self.status_override: int | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status_override:
            return httpx.Response(self.status_override, json={"errors": [{"message": "nope"}]})
        key = (request.url.path, tuple(sorted(request.url.params.items())))
        if key in self.recorded:
            return httpx.Response(200, json=self.recorded[key])
        return httpx.Response(400, json={"errors": [{"message": f"no fixture for {key}"}]})


def make_settings(tmp_path: Path, **over: Any) -> Settings:
    base: dict[str, Any] = {
        "app_env": "test",
        "qloo_api_key": TEST_KEY,
        "qloo_rps": 1000,
        "llm_provider": "fake",
        "database_path": str(tmp_path / "test.sqlite3"),
        "plans_per_ip_per_hour": 1000,
        "ollama_api_key": "",
        "gemini_api_key": "",
        "openai_compat_api_key": "",
    }
    return Settings(_env_file=None, **(base | over))  # type: ignore[call-arg]


@pytest.fixture
def fake_qloo() -> Iterator[FakeQloo]:
    fq = FakeQloo()
    with respx.mock(assert_all_called=False) as router:
        router.route(host="hackathon.api.qloo.com").mock(side_effect=fq)
        yield fq


@pytest.fixture
def make_client(tmp_path: Path, fake_qloo: FakeQloo) -> Iterator[Any]:
    clients: list[TestClient] = []
    v1._plan_hits.clear()

    def build(**over: Any) -> TestClient:
        c = TestClient(create_app(make_settings(tmp_path, **over)))
        c.__enter__()
        clients.append(c)
        return c

    yield build
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Any) -> TestClient:
    c: TestClient = make_client()
    return c
