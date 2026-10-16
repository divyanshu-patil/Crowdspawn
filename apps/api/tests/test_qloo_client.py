"""QlooClient: rate limit, retries, cache, budget, trace, silent-failure guards. Mocked HTTP."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from crowdspawn_api.errors import (
    QlooAuthError,
    QlooBudgetExceeded,
    QlooError,
    QlooFilterIgnored,
    QlooUnconfigured,
)
from crowdspawn_api.pipeline import compare
from crowdspawn_api.pipeline.cities import check_inside, regions
from crowdspawn_api.pipeline.expand import check_subtype
from crowdspawn_api.qloo.client import QlooClient
from crowdspawn_api.qloo.models import EntityInsights, HeatmapInsights
from crowdspawn_api.qloo.ratelimit import TokenBucket
from crowdspawn_api.storage import Store

from .conftest import FIXTURES, TEST_KEY, make_settings


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, s: float) -> None:
        self.now += s


async def test_token_bucket_never_exceeds_4_rps() -> None:
    clock = FakeClock()
    bucket = TokenBucket(4, clock=clock, sleep=clock.sleep)
    stamps = []
    for _ in range(40):
        await bucket.acquire()
        stamps.append(clock.now)
    for i in range(len(stamps)):
        window = [t for t in stamps if stamps[i] <= t < stamps[i] + 1.0]
        assert len(window) <= 4
    assert stamps[-1] == pytest.approx(39 * 0.25)


@pytest.fixture
async def store(tmp_path: Path) -> Any:
    s = await Store.open(tmp_path / "c.sqlite3")
    yield s
    await s.close()


async def no_sleep(_: float) -> None:
    return None


def client_for(tmp_path: Path, store: Store, **over: Any) -> QlooClient:
    return QlooClient(make_settings(tmp_path, **over), store, backoff=no_sleep)


@respx.mock
async def test_cache_hit_and_miss(tmp_path: Path, store: Store) -> None:
    route = respx.get("https://hackathon.api.qloo.com/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    run = client_for(tmp_path, store).run()
    await run.get("S1", "/search", {"query": "Hades", "take": "5"})
    await run.get("S1", "/search", {"take": "5", "query": "Hades"})  # same, reordered
    assert route.call_count == 1
    await run.get("S1", "/search", {"query": "Hades", "take": "6"})  # one param differs
    assert route.call_count == 2
    hits = [e.cache_hit for e in sorted(run.trace.entries, key=lambda e: e.result_id)]
    assert hits == [False, True, False]
    assert route.calls[0].request.headers["X-Api-Key"] == TEST_KEY
    assert TEST_KEY not in json.dumps(run.trace.dump())


@respx.mock
async def test_budget_cap_stops_run(tmp_path: Path, store: Store) -> None:
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={"results": []}))
    run = client_for(tmp_path, store).run(max_calls=3)
    for i in range(3):
        await run.get("S3", "/search", {"query": str(i)})
    with pytest.raises(QlooBudgetExceeded):
        await run.get("S3", "/search", {"query": "x"})


@respx.mock
async def test_retries_then_succeeds(tmp_path: Path, store: Store) -> None:
    route = respx.get(url__regex=r".*").mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectTimeout("t"),
            httpx.Response(200, json={"ok": 1}),
        ]
    )
    _, body = await client_for(tmp_path, store).run().get("S1", "/search", {"q": "a"})
    assert body == {"ok": 1} and route.call_count == 3


@respx.mock
async def test_gives_up_after_three_attempts(tmp_path: Path, store: Store) -> None:
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(500))
    with pytest.raises(QlooError) as e:
        await client_for(tmp_path, store).run().get("S1", "/search", {"q": "a"})
    assert e.value.code == "qloo_unavailable"


@respx.mock
async def test_auth_error_and_bad_request(tmp_path: Path, store: Store) -> None:
    respx.get(url__regex=r".*/search").mock(return_value=httpx.Response(403))
    respx.get(url__regex=r".*/v2/insights").mock(
        return_value=httpx.Response(400, json={"errors": [{"message": "bad signal"}]})
    )
    run = client_for(tmp_path, store).run()
    with pytest.raises(QlooAuthError):
        await run.get("S1", "/search", {"q": "a"})
    with pytest.raises(QlooError, match="bad signal"):
        await run.get("S2", "/v2/insights", {"q": "a"})
    assert [e.status for e in run.trace.entries] == [502, 400]


async def test_unconfigured_makes_no_call(tmp_path: Path, store: Store) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(QlooUnconfigured):
            await client_for(tmp_path, store, qloo_api_key="").run().get("S1", "/search", {})
        assert route.call_count == 0


def test_heatmap_outside_radius_is_silent_failure() -> None:
    body = json.loads((FIXTURES / "spike/heatmap/rogue_tyo.json").read_text())["body"]
    cells = HeatmapInsights.model_validate(body).results.heatmap
    check_inside(cells, regions()["tyo"])  # the real Tokyo response passes
    with pytest.raises(QlooFilterIgnored):
        check_inside(cells, regions()["lon"])  # Tokyo cells returned for a London request
    with pytest.raises(QlooFilterIgnored):
        check_inside([], regions()["lon"])


def test_wrong_entity_type_is_silent_failure() -> None:
    body = json.loads((FIXTURES / "spike/partners/artist.json").read_text())["body"]
    entities = EntityInsights.model_validate(body).results.entities
    check_subtype(entities, "urn:entity:artist")
    with pytest.raises(QlooFilterIgnored):
        check_subtype(entities, "urn:entity:podcast")


def test_contract_models_parse_every_recorded_fixture() -> None:
    for f in FIXTURES.rglob("*.json"):
        d = json.loads(f.read_text())
        if not isinstance(d, dict) or d.get("status") != 200:
            continue
        body = d["body"]
        ftype = d["request"]["params"].get("filter.type", "")
        if ftype == "urn:heatmap":
            assert HeatmapInsights.model_validate(body).results.heatmap, f
        elif ftype.startswith("urn:entity"):
            assert EntityInsights.model_validate(body).results.entities, f


@respx.mock
async def test_gap_view_from_recorded_compare(tmp_path: Path, store: Store) -> None:  # S6
    body = json.loads((FIXTURES / "spike/compare/cozy_rogue.json").read_text())["body"]
    respx.get(url__regex=r".*/v2/analysis/compare").mock(
        return_value=httpx.Response(200, json=body)
    )
    gap = await compare.gap(client_for(tmp_path, store).run(), ["A1"], ["B1"])
    assert gap.shared and gap.result_id == "q1"
    assert set(gap.target_only).isdisjoint({t["name"] for t in body["results"]["a"]})
