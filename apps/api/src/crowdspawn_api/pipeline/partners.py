"""S5: cross-domain partners the audience over-indexes on, globally and in the top cities."""

import asyncio

from ..qloo.client import QlooRun
from ..qloo.models import EntityInsights
from ..schemas import City, Partner, Partners, PartnerType, Region
from .expand import check_subtype, explain

GLOBAL_TAKE = 8
LOCAL_TAKE = 4
LOCAL_TYPES: tuple[PartnerType, ...] = ("artist", "podcast", "movie")  # brands ignore location
ALL_TYPES: tuple[PartnerType, ...] = ("artist", "podcast", "movie", "brand")


async def fetch_kind(
    run: QlooRun,
    kind: PartnerType,
    signal: list[str],
    names: dict[str, str],
    city: City | Region | None,
) -> list[Partner]:
    params = {
        "filter.type": f"urn:entity:{kind}",
        "signal.interests.entities": ",".join(signal),
        "take": str(LOCAL_TAKE if city else GLOBAL_TAKE),
        "feature.explainability": "true",
    }
    if city:
        # Verified live: filter.location is silently ignored for artists; signal.location works.
        params["signal.location"] = f"POINT({city.lon} {city.lat})"
        params["signal.location.radius"] = "30000"
    rid, body = await run.get("S5", "/v2/insights", params)
    entities = EntityInsights.model_validate(body).results.entities
    check_subtype(entities, f"urn:entity:{kind}")
    return [
        Partner(
            entity_id=e.entity_id,
            name=e.name,
            affinity=round(e.query.affinity or 0, 4),
            why=explain(e, names),
            city=city.name if city else None,
            image_url=e.image_url,
            result_id=rid,
        )
        for e in entities
    ]


async def partners(
    run: QlooRun, signal: list[str], names: dict[str, str], top_cities: list[City]
) -> Partners:
    jobs = [(k, None) for k in ALL_TYPES] + [(k, c) for c in top_cities[:3] for k in LOCAL_TYPES]
    results = await asyncio.gather(*(fetch_kind(run, k, signal, names, c) for k, c in jobs))
    out = Partners()
    for (kind, _), items in zip(jobs, results, strict=True):
        bucket: list[Partner] = getattr(out, kind)
        seen = {p.entity_id for p in bucket}
        bucket += [p for p in items if p.entity_id not in seen]
    return out
