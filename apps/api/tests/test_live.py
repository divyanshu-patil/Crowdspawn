"""Live smoke test against real Qloo and the configured LLM. Never in CI: `pnpm --filter api test:live`."""

import pytest
from fastapi.testclient import TestClient

from crowdspawn_api.main import create_app

pytestmark = pytest.mark.live


def test_live_health_and_search() -> None:
    with TestClient(create_app()) as c:
        h = c.get("/health").json()
        assert h["qloo"] == "ok", h
        hits = c.get("/v1/entities/search", params={"q": "Hades"}).json()
        assert any(x["name"] == "Hades" for x in hits)
