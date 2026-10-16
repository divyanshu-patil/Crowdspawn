"""S3: score cities from heatmap affinity_rank: comp fans, platform panels and culture anchors."""

import asyncio
import json
import math
from functools import cache
from pathlib import Path
from statistics import fmean

from ..errors import QlooError, QlooFilterIgnored
from ..qloo.client import QlooRun
from ..qloo.models import HeatmapCell, HeatmapInsights
from ..schemas import City, Region, Warning_
from ..settings import PLATFORM_PANELS
from .confidence import confidence
from .scoring import CityMetrics, Score, spawn_scores

CITIES_FILE = Path(__file__).resolve().parents[1] / "data" / "cities.json"
INSIDE_FACTOR = 1.5  # cells may sit a little outside the radius (cell centres)
MIN_INSIDE_SHARE = 0.9


@cache
def regions() -> dict[str, Region]:
    return {r["id"]: Region(**r) for r in json.loads(CITIES_FILE.read_text())}


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def check_inside(cells: list[HeatmapCell], region: Region) -> None:
    """Silent-failure guard (P6): the heatmap must actually be about the requested city."""
    if not cells:
        raise QlooFilterIgnored(f"No heatmap cells returned for {region.name}")
    limit = region.radius_m / 1000 * INSIDE_FACTOR
    inside = sum(
        km_between(region.lat, region.lon, c.location.latitude, c.location.longitude) <= limit
        for c in cells
    )
    if inside / len(cells) < MIN_INSIDE_SHARE:
        raise QlooFilterIgnored(f"Heatmap for {region.name} is not inside the requested radius")


async def heatmap_score(
    run: QlooRun, region: Region, ids: list[str] | tuple[str, ...]
) -> tuple[str, float, int]:
    rid, body = await run.get(
        "S3",
        "/v2/insights",
        {
            "filter.type": "urn:heatmap",
            "signal.interests.entities": ",".join(ids),
            "filter.location": f"POINT({region.lon} {region.lat})",
            "filter.location.radius": str(region.radius_m),
        },
    )
    cells = HeatmapInsights.model_validate(body).results.heatmap
    check_inside(cells, region)
    return rid, fmean(c.query.affinity_rank for c in cells), len(cells)


Heat = tuple[str, float, int]  # (result_id, mean affinity_rank, cells)


def make_city(region: Region, m: CityMetrics, sc: Score, result_ids: list[str]) -> City:
    return City(
        region_id=region.id,
        name=region.name,
        country=region.country,
        lat=region.lat,
        lon=region.lon,
        score=round(sc.score, 3),
        lift=round(sc.lift, 3),
        platform_fit=round(sc.platform_fit, 3),
        culture_fit=None if sc.culture_fit is None else round(sc.culture_fit, 3),
        target_score=round(m.target, 4),
        baseline_score=round(m.general, 4),
        cells=m.cells,
        confidence=confidence(sc.score, m.cells),
        result_ids=result_ids,
    )


async def score_cities(
    run: QlooRun,
    region_ids: list[str],
    signal: list[str],
    platforms: list[str] | None = None,
    culture_ids: list[str] | None = None,
) -> tuple[list[City], list[Warning_]]:
    async def one(region: Region) -> tuple[Region, CityMetrics, list[str]] | Warning_:
        sets: list[list[str] | tuple[str, ...]] = [signal, *PLATFORM_PANELS.values()]
        if culture_ids:
            sets.append(culture_ids)
        try:
            heats: list[Heat] = await asyncio.gather(
                *(heatmap_score(run, region, ids) for ids in sets)
            )
        except QlooFilterIgnored as e:
            return Warning_(
                code="qloo_filter_ignored", message=f"{region.name} skipped: {e.detail}"
            )
        except QlooError as e:
            if type(e) is not QlooError:  # auth, budget, rate limit, unconfigured: fail closed
                raise
            return Warning_(code="city_failed", message=f"{region.name} skipped: {e.detail}")
        panels = dict(zip(PLATFORM_PANELS, (h[1] for h in heats[1:4]), strict=True))
        culture = heats[4][1] if culture_ids else None
        metrics = CityMetrics(target=heats[0][1], panels=panels, cells=heats[0][2], culture=culture)
        return region, metrics, [h[0] for h in heats]

    all_regions = regions()
    results = await asyncio.gather(*(one(all_regions[i]) for i in region_ids))
    scored = [r for r in results if not isinstance(r, Warning_)]
    scores = spawn_scores({r.id: m for r, m, _ in scored}, platforms or [])
    cities = sorted(
        (make_city(r, m, scores[r.id], ids) for r, m, ids in scored),
        key=lambda c: (-c.score, c.region_id),
    )
    warnings = [r for r in results if isinstance(r, Warning_)]
    warnings += [
        Warning_(code="low_confidence_city", message=f"{c.name}: low confidence")
        for c in cities
        if c.confidence == "low"
    ]
    return cities, warnings
