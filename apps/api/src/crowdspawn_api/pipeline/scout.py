"""Region scout: player activity per area, what genres and games work there, and whether a game fits.

Same Qloo heatmap math as S3 (scoring.py), applied to any point on the map. Qloo is the only data source.
"""

import asyncio
import json
from functools import cache
from pathlib import Path
from statistics import fmean

from ..errors import QlooError
from ..qloo.client import QlooRun
from ..qloo.models import EntityInsights
from ..schemas import (
    AreaActivity,
    Calls,
    GenreHeat,
    LocalGame,
    PlaceHit,
    PlatformMix,
    Region,
    ScoutArea,
    ScoutFit,
)
from ..settings import GENRE_PANELS, PANEL_TTL_SECONDS, PLATFORM_PANELS
from .cities import heatmap_score, regions
from .confidence import confidence
from .expand import check_subtype, expand, signal_ids
from .resolve import lookup_comps
from .scoring import CityMetrics

POINTS_FILE = Path(__file__).resolve().parents[1] / "data" / "scout_points.json"
LOCALITY = "urn:entity:locality"
GAME = "urn:entity:videogame"


@cache
def scout_points() -> dict[str, Region]:
    """Plan cities plus extra points so most countries have a reading."""
    extra = {r["id"]: Region(**r) for r in json.loads(POINTS_FILE.read_text())}
    return regions() | extra


def calls(run: QlooRun) -> Calls:
    entries = run.trace.entries
    return Calls(
        live=sum(not e.cache_hit for e in entries), cached=sum(e.cache_hit for e in entries)
    )


def area(lat: float, lon: float, radius_km: int) -> Region:
    # Round so nearby clicks share cached Qloo answers (0.1 degree is about 11 km).
    return Region(
        id="area",
        name="Selected area",
        country="",
        lat=round(lat, 1),
        lon=round(lon, 1),
        radius_m=radius_km * 1000,
    )


async def mix_at(run: QlooRun, region: Region) -> tuple[PlatformMix, int]:
    heats = await asyncio.gather(
        *(heatmap_score(run, region, ids, PANEL_TTL_SECONDS) for ids in PLATFORM_PANELS.values())
    )
    by = dict(zip(PLATFORM_PANELS, (h[1] for h in heats), strict=True))
    mix = PlatformMix(
        pc=round(by["pc"], 4),
        mobile=round(by["mobile"], 4),
        console=round(by["console"], 4),
        general=round(fmean(by.values()), 4),
    )
    return mix, max(h[2] for h in heats)


async def activity(run: QlooRun) -> tuple[list[AreaActivity], list[str]]:
    async def one(r: Region) -> AreaActivity | str:
        try:
            mix, _ = await mix_at(run, r)
        except QlooError as e:
            if type(e) is not QlooError and e.code != "qloo_filter_ignored":
                raise  # auth, budget, rate limit: fail closed
            return r.name
        return AreaActivity(id=r.id, name=r.name, country=r.country, lat=r.lat, lon=r.lon, mix=mix)

    results = await asyncio.gather(*(one(r) for r in scout_points().values()))
    return [r for r in results if isinstance(r, AreaActivity)], [
        r for r in results if isinstance(r, str)
    ]


async def search_places(run: QlooRun, q: str) -> list[PlaceHit]:
    _, body = await run.get("search", "/search", {"query": q, "types": LOCALITY, "take": "6"})
    out = []
    for r in body.get("results", []) if isinstance(body, dict) else []:
        loc = r.get("location") or {}
        if LOCALITY in r.get("types", []) and "lat" in loc and "lon" in loc:
            out.append(
                PlaceHit(
                    entity_id=r["entity_id"],
                    name=r["name"],
                    label=r.get("disambiguation") or r["name"],
                    lat=loc["lat"],
                    lon=loc["lon"],
                )
            )
    return out


async def genre_heat(run: QlooRun, region: Region, general: float) -> list[GenreHeat]:
    heats = await asyncio.gather(
        *(
            heatmap_score(run, region, [i for _, i in games], PANEL_TTL_SECONDS)
            for games in GENRE_PANELS.values()
        )
    )
    out = [
        GenreHeat(genre=g, lift=round(h[1] / general, 3), examples=[n for n, _ in games[:3]])
        for (g, games), h in zip(GENRE_PANELS.items(), heats, strict=True)
    ]
    return sorted(out, key=lambda x: -x.lift)


async def local_games(run: QlooRun, region: Region) -> list[LocalGame]:
    _, body = await run.get(
        "scout",
        "/v2/insights",
        {
            "filter.type": GAME,
            "signal.location": f"POINT({region.lon} {region.lat})",
            "signal.location.radius": str(region.radius_m),
            "take": "10",
        },
    )
    entities = EntityInsights.model_validate(body).results.entities
    check_subtype(entities, GAME)
    return [
        LocalGame(
            entity_id=e.entity_id,
            name=e.name,
            affinity=round(e.query.affinity or 0, 4),
            image_url=e.image_url,
        )
        for e in entities
    ]


WIDE_KM = 120


async def mix_widening(
    run: QlooRun, lat: float, lon: float, radius_km: int
) -> tuple[Region, PlatformMix, int]:
    """Between towns Qloo has few cells; widen once before giving up (qloo_filter_ignored)."""
    try:
        r = area(lat, lon, radius_km)
        return r, *(await mix_at(run, r))
    except QlooError as e:
        if e.code != "qloo_filter_ignored" or radius_km >= WIDE_KM:
            raise
    r = area(lat, lon, WIDE_KM)
    return r, *(await mix_at(run, r))


async def scout_area(run: QlooRun, lat: float, lon: float, radius_km: int) -> ScoutArea:
    r, mix, cells = await mix_widening(run, lat, lon, radius_km)
    genres, games = await asyncio.gather(genre_heat(run, r, mix.general), local_games(run, r))
    return ScoutArea(
        lat=r.lat,
        lon=r.lon,
        radius_km=r.radius_m // 1000,
        cells=cells,
        mix=mix,
        genres=genres,
        games=games,
        calls=calls(run),
    )


def verdict(score: float) -> str:
    if score >= 1.10:
        return "strong"
    if score >= 1.03:
        return "promising"
    if score > 0.97:
        return "neutral"
    return "weak"


async def scout_fit(
    run: QlooRun, lat: float, lon: float, radius_km: int, comp_ids: list[str], platforms: list[str]
) -> ScoutFit:
    comps, _ = await lookup_comps(run, comp_ids)
    if not comps:
        raise QlooError("None of the comps resolved to a Qloo video game", code="comp_unresolved")
    signal = signal_ids(comps, await expand(run, comps))
    r, mix, _ = await mix_widening(run, lat, lon, radius_km)
    _, target, cells = await heatmap_score(run, r, signal)
    m = CityMetrics(
        target=target,
        panels={"pc": mix.pc, "mobile": mix.mobile, "console": mix.console},
        cells=cells,
    )
    pfit = m.platform_fit(platforms)
    score = m.lift * pfit
    genres = await genre_heat(run, r, mix.general)
    return ScoutFit(
        lat=r.lat,
        lon=r.lon,
        comps=[c.name for c in comps],
        lift=round(m.lift, 3),
        platform_fit=round(pfit, 3),
        score=round(score, 3),
        verdict=verdict(score),  # type: ignore[arg-type]
        confidence=confidence(score, cells),
        cells=cells,
        best_genre=genres[0] if genres else None,
        calls=calls(run),
    )
