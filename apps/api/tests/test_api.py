"""API tests over recorded Qloo fixtures and the FakeProvider. No network."""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from crowdspawn_api.llm.fake import FakeProvider
from crowdspawn_api.main import create_app

from .conftest import PLAN_INPUT, TEST_KEY, FakeQloo, make_settings


def run_plan(client: TestClient, body: dict[str, Any] | None = None) -> dict[str, Any]:
    r = client.post("/v1/plans", json=body or PLAN_INPUT)
    assert r.status_code == 202, r.text
    plan_id = r.json()["id"]
    # BackgroundTasks finish before TestClient returns, so the plan is complete here.
    plan: dict[str, Any] = client.get(f"/v1/plans/{plan_id}").json()
    return plan


def sse_events(client: TestClient, plan_id: str, last_id: int = 0) -> list[tuple[int, str, dict]]:
    headers = {"Last-Event-ID": str(last_id)} if last_id else {}
    with client.stream("GET", f"/v1/plans/{plan_id}/stream", headers=headers) as r:
        text = "".join(r.iter_text())
    out = []
    for block in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields:
            out.append((int(fields["id"]), fields["event"], json.loads(fields["data"])))
    return out


def qloo_items(plan: dict[str, Any]) -> list[dict[str, Any]]:
    items = plan["comps"] + plan["expanded"] + plan["cities"] + [plan["audience"]]
    for kind in ("artist", "podcast", "movie", "brand"):
        items += plan["partners"][kind]
    return items


def test_full_plan_is_qloo_sourced_and_traced(client: TestClient) -> None:
    plan = run_plan(client)
    assert plan["status"] == "done", plan.get("error")
    trace = client.get(f"/v1/plans/{plan['id']}/trace").json()
    ids = {t["result_id"] for t in trace}
    for item in qloo_items(plan):
        assert item["source"] == "qloo"
        refs = item.get("result_ids") or [item["result_id"]]
        assert set(refs) <= ids
    # at least five distinct Qloo capabilities
    kinds = {(t["endpoint"], t["params"].get("filter.type")) for t in trace}
    assert ("/entities", None) in kinds
    assert ("/v2/insights", "urn:entity:videogame") in kinds
    assert ("/v2/insights", "urn:heatmap") in kinds
    assert ("/v2/insights", "urn:demographics") in kinds
    assert ("/v2/insights", "urn:entity:artist") in kinds
    # steps run in dependency order and S2 uses S1 ids
    steps = [t["step"] for t in sorted(trace, key=lambda t: int(t["result_id"][1:]))]
    assert steps == sorted(steps)
    s2 = next(t for t in trace if t["step"] == "S2")
    assert s2["params"]["signal.interests.entities"].split(",") == PLAN_INPUT["comp_entity_ids"]
    # trace rows carry endpoint, step, cache flag and status, and never the key
    assert all({"endpoint", "step", "cache_hit", "status"} <= t.keys() for t in trace)
    assert TEST_KEY not in json.dumps(trace) + json.dumps(plan)
    # budget shares and a grounded brief
    assert abs(sum(c["budget_share"] for c in plan["cities"]) - 100) < 0.005
    assert plan["brief"]["source"] == "llm"
    assert plan["limits"][0].startswith("Affinity index")
    # J18: launch actions read these from the plan (languages are static reference data)
    assert all(c["languages"] and c["radius_m"] for c in plan["cities"])
    assert any("static table, not Qloo" in line for line in plan["limits"])


def test_repeat_plan_makes_zero_live_calls(client: TestClient, fake_qloo: FakeQloo) -> None:
    first = run_plan(client)
    n = len(fake_qloo.requests)
    second = run_plan(client)
    assert len(fake_qloo.requests) == n
    assert second["calls"]["live"] == 0 and second["calls"]["cached"] == first["calls"]["live"]


def test_kill_switch_no_key(make_client: Any) -> None:
    client = make_client(qloo_api_key="")
    fake = FakeProvider()
    client.app.state.deps.llm = fake
    plan = run_plan(client)
    assert plan["status"] == "failed"
    assert plan["error"]["code"] == "qloo_unconfigured"
    assert plan["cities"] == [] and plan["brief"] is None and plan["comps"] == []
    assert fake.calls == []  # no content LLM call
    assert client.get("/health").json()["qloo"] == "unconfigured"


def test_kill_switch_invalid_key(client: TestClient, fake_qloo: FakeQloo) -> None:
    fake_qloo.status_override = 401
    fake = FakeProvider()
    client.app.state.deps.llm = fake
    plan = run_plan(client)
    assert plan["status"] == "failed" and plan["error"]["code"] == "qloo_auth"
    assert plan["brief"] is None and fake.calls == []
    events = sse_events(client, plan["id"])
    assert events[-1][1] == "failed" and events[-1][2]["code"] == "qloo_auth"
    trace = client.get(f"/v1/plans/{plan['id']}/trace").json()
    assert trace[-1]["status"] == 401  # the trace shows what Qloo said [J2]


def test_daily_cap_fails_the_plan_closed(make_client: Any, fake_qloo: FakeQloo) -> None:
    """J8: at the global daily cap a plan fails like a budget stop, and /health shows 0 left."""
    client = make_client(qloo_daily_call_cap=3)
    assert client.get("/health").json()["qloo_calls_left_today"] == 2  # health spent one
    plan = run_plan(client)
    assert plan["status"] == "failed" and plan["error"]["code"] == "qloo_daily_cap"
    assert plan["cities"] == [] and plan["brief"] is None
    assert len(fake_qloo.requests) == 3
    assert client.get("/health").json()["qloo_calls_left_today"] == 0


def test_llm_calls_limited_to_brief(client: TestClient) -> None:
    fake = FakeProvider()
    client.app.state.deps.llm = fake
    run_plan(client)
    assert 1 <= len(fake.calls) <= 4
    assert all("<facts>" in "".join(m["content"] for m in call) for call in fake.calls)


def test_bad_brief_falls_back_to_template(client: TestClient) -> None:
    invented = json.dumps(
        {
            "sections": [
                {"heading": "Where", "body": "Go to **Melbourne**, lift 9.99 [q1]."},
                {"heading": "Caveats", "body": "None."},
            ]
        }
    )
    fake = FakeProvider(replies=[invented, invented, invented, invented])
    client.app.state.deps.llm = fake
    plan = run_plan(client)
    assert plan["brief"]["source"] == "template" and plan["brief"]["notice"]
    assert len(fake.calls) == 2  # first try + one grounded regeneration
    assert any(w["code"] == "brief_template" for w in plan["warnings"])


def test_provider_swap_changes_only_brief(make_client: Any) -> None:
    a, b = make_client(), make_client()
    a.app.state.deps.llm = FakeProvider(prefix="Alpha. ")
    b.app.state.deps.llm = FakeProvider(prefix="Beta. ")
    pa, pb = run_plan(a), run_plan(b)
    assert pa["brief"] != pb["brief"]
    strip = {"id", "created_at", "brief", "calls"}
    assert {k: v for k, v in pa.items() if k not in strip} == {
        k: v for k, v in pb.items() if k not in strip
    }


def test_unresolved_comp_is_dropped(client: TestClient, fake_qloo: FakeQloo) -> None:
    body = PLAN_INPUT | {"comp_entity_ids": PLAN_INPUT["comp_entity_ids"] + ["NOT-A-REAL-ID"]}
    lookup_key = next(k for k in fake_qloo.recorded if k[0] == "/entities")
    fake_qloo.recorded[("/entities", (("entity_ids", ",".join(body["comp_entity_ids"])),))] = (
        fake_qloo.recorded[lookup_key]
    )
    plan = run_plan(client, body)
    assert "NOT-A-REAL-ID" in plan["dropped_comps"]
    assert all(c["entity_id"] != "NOT-A-REAL-ID" for c in plan["comps"])
    assert any(w["code"] == "unresolved_comp" for w in plan["warnings"])


def test_sse_replays_all_event_types_and_resumes(client: TestClient) -> None:
    plan = run_plan(client)
    events = sse_events(client, plan["id"])  # late connection: replays everything
    types = {t for _, t, _ in events}
    assert {"step_started", "qloo_call", "step_done", "warning", "done"} <= types
    mid = events[len(events) // 2][0]
    resumed = sse_events(client, plan["id"], last_id=mid)
    assert resumed[0][0] == mid + 1 and resumed == [e for e in events if e[0] > mid]


def test_validation_problems(client: TestClient) -> None:
    cases = [
        PLAN_INPUT | {"comp_entity_ids": []},
        PLAN_INPUT | {"regions": ["nyc", "lon"]},
        PLAN_INPUT | {"regions": ["nyc", "lon", "atlantis"]},
        PLAN_INPUT | {"comp_entity_ids": ["a", "a"]},
        PLAN_INPUT | {"mode": "turbo"},
        PLAN_INPUT | {"game": {"title": "x" * 81}},
    ]
    for body in cases:
        r = client.post("/v1/plans", json=body)
        assert r.status_code == 422, body
        assert r.json()["code"] == "validation_error" and r.json()["detail"]


def test_not_found(client: TestClient) -> None:
    r = client.get("/v1/plans/nope")
    assert r.status_code == 404 and r.json()["code"] == "plan_not_found"
    assert client.get("/v1/plans/nope/trace").status_code == 404


def test_rate_limit_per_ip(make_client: Any) -> None:
    client = make_client(plans_per_ip_per_hour=1)
    assert client.post("/v1/plans", json=PLAN_INPUT).status_code == 202
    r = client.post("/v1/plans", json=PLAN_INPUT)
    assert r.status_code == 429 and r.json()["code"] == "rate_limited"


def test_regions_and_health(client: TestClient) -> None:
    regions = client.get("/v1/regions").json()
    assert len(regions) >= 15 and {"id", "lat", "lon", "radius_m"} <= regions[0].keys()
    h = client.get("/health").json()
    assert h["llm"] == {"provider": "fake", "model": "fake-1", "status": "configured"}
    assert client.get("/health").headers["X-Request-ID"]


def test_suggest_drops_unresolvable_names(client: TestClient, fake_qloo: FakeQloo) -> None:
    hades = {"results": [{"name": "Hades", "entity_id": "H1", "types": ["urn:entity:videogame"]}]}
    for name in ("Hades", "Dead Cells", "Slay the Spire", "Not A Real Game 9000"):
        hits = (
            hades
            if name == "Hades"
            else {
                "results": [
                    {"name": "Something Else", "entity_id": "X", "types": ["urn:entity:videogame"]}
                ]
            }
        )
        params = (("query", name), ("take", "5"), ("types", "urn:entity:videogame"))
        fake_qloo.recorded[("/search", params)] = hits
    r = client.post("/v1/comps/suggest", json={"title": "Ember Crypt"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [s["resolved"]["name"] for s in body["suggestions"]] == ["Hades"]
    assert "Not A Real Game 9000" in body["dropped"]


def test_culture_suggest_resolves_through_qloo(client: TestClient, fake_qloo: FakeQloo) -> None:
    movie = "urn:entity:movie"
    hit = {"results": [{"name": "Gully Boy", "entity_id": "G1", "types": [movie]}]}
    miss = {"results": [{"name": "Gully Boys", "entity_id": "X", "types": [movie]}]}
    for name, body in (("Gully Boy", hit), ("Not A Real Film 404", miss)):
        fake_qloo.recorded[("/search", (("query", name), ("take", "5"), ("types", movie)))] = body
    r = client.post("/v1/culture/suggest", json={"title": "Delhi Gullies", "tags": ["india"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(s["input_name"], s["resolved"]["entity_id"]) for s in body["suggestions"]] == [
        ("Gully Boy", "G1")
    ]
    assert body["dropped"] == ["Not A Real Film 404"]


def test_culture_search_spans_films_shows_artists(client: TestClient, fake_qloo: FakeQloo) -> None:
    for t in ("urn:entity:movie", "urn:entity:tv_show", "urn:entity:artist"):
        name = "Sacred Games" if t.endswith("tv_show") else "Sacred Gamesters"
        fake_qloo.recorded[
            ("/search", (("query", "sacred games"), ("take", "4"), ("types", t)))
        ] = {"results": [{"name": name, "entity_id": t[-5:], "types": [t]}]}
    r = client.get("/v1/entities/search", params={"q": "sacred games", "type": "culture"})
    assert r.status_code == 200, r.text
    assert r.json()[0] == {
        "entity_id": "_show",
        "name": "Sacred Games",
        "type": "urn:entity:tv_show",
        "year": None,
        "image_url": None,
    }
    assert client.get("/v1/entities/search", params={"q": "x", "type": "place"}).status_code == 422


def test_old_plans_without_spawn_score_still_load() -> None:
    from crowdspawn_api.schemas import City

    c = City.model_validate(
        {
            "region_id": "nyc",
            "name": "New York",
            "country": "US",
            "lat": 0,
            "lon": 0,
            "lift": 1.2,
            "target_score": 0.8,
            "baseline_score": 0.7,
            "cells": 10,
            "confidence": "low",
            "result_ids": ["q1"],
        }
    )
    assert (c.score, c.platform_fit, c.culture_fit) == (1.2, 1.0, None)


def test_suggest_without_llm(client: TestClient) -> None:
    client.app.state.deps.llm = None
    r = client.post("/v1/comps/suggest", json={"title": "Ember Crypt"})
    assert r.status_code == 502 and r.json()["code"] == "llm_unavailable"


def test_entity_search(client: TestClient, fake_qloo: FakeQloo) -> None:
    params = (("query", "hades"), ("take", "8"), ("types", "urn:entity:videogame"))
    fake_qloo.recorded[("/search", params)] = {
        "results": [
            {
                "name": "Hades",
                "entity_id": "H1",
                "types": ["urn:entity:videogame"],
                "properties": {"release_year": 2018, "image": {"url": "https://img"}},
            }
        ]
    }
    r = client.get("/v1/entities/search", params={"q": "hades"})
    assert r.json() == [
        {
            "entity_id": "H1",
            "name": "Hades",
            "type": "urn:entity:videogame",
            "year": 2018,
            "image_url": "https://img",
        }
    ]


def test_form_path_works_without_any_llm(client: TestClient, fake_qloo: FakeQloo) -> None:
    """J16: the front door's fallback. With no LLM the agent refuses, but comp search and plans work."""
    client.app.state.deps.llm = None
    r = client.post("/v1/agent", json={"goal": "A cozy farming game for PC and Switch"})
    assert r.json()["code"].startswith("llm_")
    params = (("query", "hades"), ("take", "8"), ("types", "urn:entity:videogame"))
    fake_qloo.recorded[("/search", params)] = {
        "results": [{"name": "Hades", "entity_id": "H1", "types": ["urn:entity:videogame"]}]
    }
    assert client.get("/v1/entities/search", params={"q": "hades"}).json()[0]["name"] == "Hades"
    plan = run_plan(client)
    assert plan["status"] == "done" and plan["brief"]["source"] == "template"


def test_openapi_contract_is_current(tmp_path: Path) -> None:
    committed = Path(__file__).parents[1] / "openapi.json"
    live = create_app(make_settings(tmp_path)).openapi()
    assert json.loads(committed.read_text()) == live, "run: pnpm --filter api openapi"
    paths = set(live["paths"])
    assert {
        "/health",
        "/v1/entities/search",
        "/v1/comps/suggest",
        "/v1/plans",
        "/v1/plans/{plan_id}",
        "/v1/plans/{plan_id}/stream",
        "/v1/plans/{plan_id}/trace",
        "/v1/regions",
    } <= paths
