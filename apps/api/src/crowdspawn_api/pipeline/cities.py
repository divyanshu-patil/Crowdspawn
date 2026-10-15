"""S3: score cities by heatmap affinity_rank, as lift over a mainstream-gamer baseline."""

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
from ..settings import BASELINE_ENTITY_IDS
from .confidence import confidence

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


def make_city(region: Region, target: tuple[str, float, int], base: tuple[str, float, int]) -> City:
    lift = target[1] / base[1] if base[1] > 0 else 0.0
    return City(
        region_id=region.id,
        name=region.name,
        country=region.country,
        lat=region.lat,
        lon=region.lon,
        lift=round(lift, 3),
        target_score=round(target[1], 4),
        baseline_score=round(base[1], 4),
        cells=target[2],
        confidence=confidence(lift, target[2]),
        result_ids=[target[0], base[0]],
    )


async def score_cities(
    run: QlooRun, region_ids: list[str], signal: list[str]
) -> tuple[list[City], list[Warning_]]:
    async def one(region: Region) -> City | Warning_:
        try:
            target, base = await asyncio.gather(
                heatmap_score(run, region, signal), heatmap_score(run, region, BASELINE_ENTITY_IDS)
            )
        except QlooFilterIgnored as e:
            return Warning_(
                code="qloo_filter_ignored", message=f"{region.name} skipped: {e.detail}"
            )
        except QlooError as e:
            if type(e) is not QlooError:  # auth, budget, rate limit, unconfigured: fail closed
                raise
            return Warning_(code="city_failed", message=f"{region.name} skipped: {e.detail}")
        return make_city(region, target, base)

    all_regions = regions()
    results = await asyncio.gather(*(one(all_regions[i]) for i in region_ids))
    cities = sorted(
        (r for r in results if isinstance(r, City)), key=lambda c: (-c.lift, c.region_id)
    )
    warnings = [r for r in results if isinstance(r, Warning_)]
    warnings += [
        Warning_(code="low_confidence_city", message=f"{c.name}: low confidence")
        for c in cities
        if c.confidence == "low"
    ]
    return cities, warnings
