"""S2: expand comps into a wider set of similar games, keeping Qloo's explainability."""

from ..errors import QlooFilterIgnored
from ..qloo.client import QlooRun
from ..qloo.models import Entity, EntityInsights
from ..schemas import Comp, ExpandedGame

EXPANDED_TAKE = 20
SIGNAL_EXTRA = 7  # comps + this many expanded games form the signal for S3-S5
DESCRIPTOR_KEYS = ("audience_tags", "emotional_tone", "genre")


def explain(entity: Entity, names: dict[str, str]) -> str:
    """Turn Qloo's explainability scores and descriptors into one plain sentence."""
    parts = [
        f"{names[c.entity_id]} {round(c.score * 100)}%"
        for c in sorted(entity.contributions, key=lambda c: -c.score)
        if c.entity_id in names and c.score > 0
    ][:3]
    text = f"Driven by fans of {', '.join(parts)}" if parts else "Matched on the comp set"
    descriptors: list[str] = []
    for k in DESCRIPTOR_KEYS:
        v = entity.properties.get(k)
        if isinstance(v, list):
            descriptors += [str(x) for x in v]
    if not descriptors:
        descriptors = [t.name for t in entity.tags if t.name]
    if descriptors:
        text += f". Qloo tags: {', '.join(dict.fromkeys(descriptors[:4]))}"
    return text + "."


def check_subtype(entities: list[Entity], expected: str) -> None:
    """Silent-failure guard (P6): a 200 with the wrong entity type means the filter was ignored."""
    bad = [e.name for e in entities if e.subtype and e.subtype != expected]
    if bad:
        raise QlooFilterIgnored(f"Asked for {expected}, got {bad[:3]}")


async def expand(run: QlooRun, comps: list[Comp]) -> list[ExpandedGame]:
    rid, body = await run.get(
        "S2",
        "/v2/insights",
        {
            "filter.type": "urn:entity:videogame",
            "signal.interests.entities": ",".join(c.entity_id for c in comps),
            "take": str(EXPANDED_TAKE),
            "feature.explainability": "true",
        },
    )
    entities = EntityInsights.model_validate(body).results.entities
    check_subtype(entities, "urn:entity:videogame")
    names = {c.entity_id: c.name for c in comps}
    comp_ids = set(names)
    return [
        ExpandedGame(
            entity_id=e.entity_id,
            name=e.name,
            affinity=round(e.query.affinity or 0, 4),
            why=explain(e, names),
            image_url=e.image_url,
            result_id=rid,
        )
        for e in entities
        if e.entity_id not in comp_ids
    ]


def signal_ids(comps: list[Comp], expanded: list[ExpandedGame]) -> list[str]:
    return [c.entity_id for c in comps] + [g.entity_id for g in expanded[:SIGNAL_EXTRA]]
