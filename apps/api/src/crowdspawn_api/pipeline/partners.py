"""S5: cross-domain partners the audience over-indexes on against all gamers, globally and in the top cities."""

import asyncio

from ..qloo.client import QlooRun
from ..qloo.models import Entity, EntityInsights
from ..schemas import City, Partner, Partners, PartnerType, Region
from ..settings import PANEL_TTL_SECONDS, PLATFORM_PANELS
from .expand import check_subtype, explain

POOL = 30  # Qloo's top names by comp affinity; the highest lift among them are kept
GLOBAL_TAKE = 8
LOCAL_TAKE = 4
LOCAL_TYPES: tuple[PartnerType, ...] = ("artist", "podcast", "movie")  # brands ignore location
ALL_TYPES: tuple[PartnerType, ...] = ("artist", "podcast", "movie", "brand")
GAMERS = ",".join(dict.fromkeys(i for ids in PLATFORM_PANELS.values() for i in ids))


async def fetch_kind(
    run: QlooRun,
    kind: PartnerType,
    signal: list[str],
    names: dict[str, str],
    city: City | Region | None,
) -> list[Partner]:
    """The comp fans' top POOL, ranked by lift = their affinity / all gamers' affinity in the same place."""
    where = {"filter.type": f"urn:entity:{kind}"}
    if city:
        # Verified live: filter.location is silently ignored for artists; signal.location works.
        where["signal.location"] = f"POINT({city.lon} {city.lat})"
        where["signal.location.radius"] = "30000"
    rid, body = await run.get(
        "S5",
        "/v2/insights",
        where
        | {
            "signal.interests.entities": ",".join(signal),
            "take": str(POOL),
            "feature.explainability": "true",
        },
    )
    entities = EntityInsights.model_validate(body).results.entities
    check_subtype(entities, f"urn:entity:{kind}")
    if not entities:
        return []
    # Verified live (J11): filter.entities scores exactly these ids against the all-gamers panels.
    _, base = await run.get(
        "S5",
        "/v2/insights",
        where
        | {
            "signal.interests.entities": GAMERS,
            "filter.entities": ",".join(e.entity_id for e in entities),
            "take": str(len(entities)),
        },
        PANEL_TTL_SECONDS,
    )
    gamers = {
        e.entity_id: e.query.affinity for e in EntityInsights.model_validate(base).results.entities
    }

    def lift(e: Entity) -> float | None:
        g = gamers.get(e.entity_id)
        return round(e.query.affinity / g, 4) if e.query.affinity and g else None

    ranked = sorted(((e, lift(e)) for e in entities), key=lambda x: -(x[1] or 0))
    return [
        Partner(
            entity_id=e.entity_id,
            name=e.name,
            affinity=round(e.query.affinity or 0, 4),
            lift=lf,
            why=explain(e, names),
            city=city.name if city else None,
            image_url=e.image_url,
            result_id=rid,
        )
        for e, lf in ranked
    ]


async def partners(
    run: QlooRun, signal: list[str], names: dict[str, str], top_cities: list[City]
) -> Partners:
    jobs = [(k, None) for k in ALL_TYPES] + [(k, c) for c in top_cities[:3] for k in LOCAL_TYPES]
    results = await asyncio.gather(*(fetch_kind(run, k, signal, names, c) for k, c in jobs))
    out = Partners()
    for (kind, city), items in zip(jobs, results, strict=True):
        bucket: list[Partner] = getattr(out, kind)
        seen = {p.entity_id for p in bucket}  # globals come first: a local list never repeats them
        bucket += [p for p in items if p.entity_id not in seen][
            : LOCAL_TAKE if city else GLOBAL_TAKE
        ]
    return out
