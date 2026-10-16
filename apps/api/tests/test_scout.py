"""Region scout: activity, area genres and games, fit verdicts, place search (replayed Qloo)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from crowdspawn_api.pipeline import scout
from crowdspawn_api.routes import v1
from crowdspawn_api.schemas import Region
from crowdspawn_api.settings import GENRE_PANELS, PLATFORM_PANELS

from .conftest import FakeQloo

GAME = "urn:entity:videogame"


def heat_key(
    r: Region, ids: list[str] | tuple[str, ...]
) -> tuple[str, tuple[tuple[str, str], ...]]:
    params = {
        "filter.type": "urn:heatmap",
        "signal.interests.entities": ",".join(ids),
        "filter.location": f"POINT({r.lon} {r.lat})",
        "filter.location.radius": str(r.radius_m),
    }
    return "/v2/insights", tuple(sorted(params.items()))


def cells(r: Region, rank: float, n: int = 200) -> dict[str, Any]:
    cell = {
        "location": {"latitude": r.lat, "longitude": r.lon},
        "query": {"affinity": 0.5, "affinity_rank": rank},
    }
    return {"results": {"heatmap": [cell] * n}}


def stage_area(fq: FakeQloo, r: Region, genre_rank: dict[str, float]) -> None:
    for p, rank in {"pc": 0.9, "mobile": 0.9, "console": 0.6}.items():
        fq.recorded[heat_key(r, PLATFORM_PANELS[p])] = cells(r, rank)
    for g, games in GENRE_PANELS.items():
        fq.recorded[heat_key(r, [i for _, i in games])] = cells(r, genre_rank.get(g, 0.8))
    local = {
        "filter.type": GAME,
        "signal.location": f"POINT({r.lon} {r.lat})",
        "signal.location.radius": str(r.radius_m),
        "take": "10",
    }
    fq.recorded[("/v2/insights", tuple(sorted(local.items())))] = {
        "results": {
            "entities": [
                {"name": "PUBG", "entity_id": "P1", "subtype": GAME, "query": {"affinity": 0.97}}
            ]
        }
    }


def test_area_ranks_genres_against_all_gamers(client: TestClient, fake_qloo: FakeQloo) -> None:
    r = scout.area(28.61, 77.21, 40)
    stage_area(fake_qloo, r, {"Battle royale": 1.0, "MOBA": 0.6})
    res = client.post("/v1/scout/area", json={"lat": 28.61, "lon": 77.21})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["lat"], body["lon"], body["radius_km"]) == (
        28.6,
        77.2,
        40,
    )  # rounded for cache reuse
    assert body["mix"] == {"pc": 0.9, "mobile": 0.9, "console": 0.6, "general": 0.8}
    assert body["genres"][0] == {
        "genre": "Battle royale",
        "lift": 1.25,
        "examples": ["Fortnite", "Call of Duty: Warzone", "Fall Guys"],
    }
    assert body["genres"][-1]["genre"] == "MOBA" and body["genres"][-1]["lift"] == 0.75
    assert [g["name"] for g in body["games"]] == ["PUBG"]
    assert body["calls"]["live"] == 3 + len(GENRE_PANELS) + 1
    again = client.post(
        "/v1/scout/area", json={"lat": 28.64, "lon": 77.18}
    ).json()  # same 0.1 degree cell
    assert again["calls"]["live"] == 0


def test_area_rejects_bad_coordinates_and_failed_calls(client: TestClient) -> None:
    res = client.post("/v1/scout/area", json={"lat": 0, "lon": -30})
    assert res.status_code == 502  # unknown request: the fake Qloo answers 400
    assert client.post("/v1/scout/area", json={"lat": 91, "lon": 0}).status_code == 422


def test_area_with_empty_heatmap_is_no_area_data(client: TestClient, fake_qloo: FakeQloo) -> None:
    for radius in (40, scout.WIDE_KM):  # widened once before giving up
        r = scout.area(0, -30, radius)
        for p in PLATFORM_PANELS.values():
            fake_qloo.recorded[heat_key(r, p)] = {"results": {"heatmap": []}}
    res = client.post("/v1/scout/area", json={"lat": 0, "lon": -30})
    assert res.status_code == 422 and res.json()["code"] == "no_area_data"


def test_area_widens_between_towns(client: TestClient, fake_qloo: FakeQloo) -> None:
    near = scout.area(17.6, 76.0, 40)
    for p in PLATFORM_PANELS.values():
        fake_qloo.recorded[heat_key(near, p)] = {"results": {"heatmap": []}}
    stage_area(fake_qloo, scout.area(17.6, 76.0, scout.WIDE_KM), {})
    res = client.post("/v1/scout/area", json={"lat": 17.6, "lon": 76.0})
    assert res.status_code == 200, res.text
    assert res.json()["radius_km"] == scout.WIDE_KM


def test_fit_scores_the_comp_set_here(client: TestClient, fake_qloo: FakeQloo) -> None:
    r = scout.area(28.61, 77.21, 40)
    stage_area(fake_qloo, r, {"Battle royale": 1.0})
    fake_qloo.recorded[("/entities", (("entity_ids", "C1"),))] = {
        "results": [{"name": "Grand Theft Auto V", "entity_id": "C1", "types": [GAME]}]
    }
    expand_params = {
        "filter.type": GAME,
        "signal.interests.entities": "C1",
        "take": "20",
        "feature.explainability": "true",
    }
    fake_qloo.recorded[("/v2/insights", tuple(sorted(expand_params.items())))] = {
        "results": {"entities": []}
    }
    fake_qloo.recorded[heat_key(r, ["C1"])] = cells(r, 0.92)
    res = client.post(
        "/v1/scout/fit",
        json={"lat": 28.61, "lon": 77.21, "comp_entity_ids": ["C1"], "platforms": ["pc"]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["lift"] == pytest.approx(1.15)  # 0.92 / 0.8
    assert body["platform_fit"] == pytest.approx(1.125)  # pc 0.9 / 0.8
    assert body["score"] == pytest.approx(1.294, abs=1e-3)
    assert (body["verdict"], body["confidence"]) == ("strong", "high")
    assert body["best_genre"]["genre"] == "Battle royale"


@pytest.mark.parametrize(
    ("score", "verdict"),
    [(1.1, "strong"), (1.0999, "promising"), (1.03, "promising"), (1.0, "neutral"), (0.97, "weak")],
)
def test_verdict_thresholds(score: float, verdict: str) -> None:
    assert scout.verdict(score) == verdict


def test_places_keep_only_localities_with_coordinates(
    client: TestClient, fake_qloo: FakeQloo
) -> None:
    loc = "urn:entity:locality"
    fake_qloo.recorded[("/search", (("query", "Lagos"), ("take", "6"), ("types", loc)))] = {
        "results": [
            {
                "name": "Lagos",
                "entity_id": "L1",
                "types": [loc],
                "disambiguation": "Lagos, Nigeria",
                "location": {"lat": 6.5, "lon": 3.6},
            },
            {"name": "Lagos", "entity_id": "L2", "types": [loc]},
        ]
    }
    res = client.get("/v1/scout/places", params={"q": "Lagos"})
    assert res.json() == [
        {"entity_id": "L1", "name": "Lagos", "region": "", "lat": 6.5, "lon": 3.6}
    ]


def aka(value: str, language: str | None = None) -> dict[str, str]:
    return {"value": value} | ({"language": language} if language else {})


@pytest.mark.parametrize(
    ("hit", "query", "name"),
    [
        (
            {"name": "Київ", "properties": {"akas": [aka("Kiew", "de"), aka("Kyiv", "nl")]}},
            "Kyiv",
            "Kyiv",
        ),
        (
            {"name": "서울", "properties": {"akas": [aka("Seoul Special City", "en")]}},
            "Seoul",
            "Seoul Special City",
        ),
        ({"name": "Москва", "properties": {"akas": [aka("Moscó", "gl")]}}, "moscow", "Moscow"),
        ({"name": "東京都", "properties": {"akas": [aka("東京都")]}}, "tokyo", "Tokyo"),
        ({"name": "São Paulo"}, "sao paulo", "Sao Paulo"),
        ({"name": "Hachiōji, Tokyo"}, "tokyo", "Hachioji, Tokyo"),
        ({"name": "القاهرة", "properties": {"akas": [aka("Le Caire", "fr")]}}, "xyz", "Le Caire"),
    ],
)
def test_place_names_are_plain_english(hit: dict[str, Any], query: str, name: str) -> None:
    assert scout.english_name(hit, query) == name


def test_place_region_is_the_latin_state_without_country() -> None:
    def hit(name: str, *ancestors: tuple[str, str | None]) -> dict[str, Any]:
        return {
            "name": name,
            "properties": {"ancestors": [{"name": n, "place": p} for n, p in ancestors]},
        }

    us = hit(
        "Cairo", ("Grady", "county"), ("Georgia", "state"), ("United States of America", "country")
    )
    assert scout.english_region(us) == "Georgia"
    assert scout.english_region(hit("Lagos", ("Faro", None), ("Portugal", "country"))) == "Faro"
    assert scout.english_region(hit("Київ", ("Київська", None), ("Україна", "country"))) == ""
    assert scout.english_region(hit("Riyadh", ("Riyadh", "state"), ("Saudi", "country"))) == ""
    assert scout.english_region(hit("Mumbai", ("Maharashtra", "state"))) == "Maharashtra"


def test_activity_reports_skipped_points(
    client: TestClient, fake_qloo: FakeQloo, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = Region(id="del", name="Delhi", country="IN", lat=28.61, lon=77.21, radius_m=30000)
    sea = Region(id="sea", name="Mid-Atlantic", country="", lat=0, lon=-30, radius_m=30000)
    monkeypatch.setattr(scout, "scout_points", lambda: {"del": good, "sea": sea})
    for p in PLATFORM_PANELS.values():
        fake_qloo.recorded[heat_key(good, p)] = cells(good, 0.9)
        fake_qloo.recorded[heat_key(sea, p)] = {"results": {"heatmap": []}}
    body = client.get("/v1/scout/activity").json()
    assert [p["id"] for p in body["points"]] == ["del"] and body["points"][0]["mix"][
        "general"
    ] == 0.9
    assert body["skipped"] == ["Mid-Atlantic"]


def test_scout_is_rate_limited(make_client: Any) -> None:
    c = make_client(scouts_per_ip_per_hour=1)
    v1._scout_hits.clear()
    c.post("/v1/scout/area", json={"lat": 1, "lon": 1})
    res = c.post("/v1/scout/area", json={"lat": 1, "lon": 1})
    assert res.status_code == 429


def test_scout_points_cover_plan_cities_and_more() -> None:
    pts = scout.scout_points()
    assert len(pts) == 67 and {"del", "los", "sha"} <= set(pts)
