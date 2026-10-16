"""Culture anchors: films, shows and artists from a game's setting, resolved through Qloo search.

Their heatmap tells S3 where fans of that culture are (an Indian setting lights up Delhi and Mumbai,
and the diaspora in London and Dubai). Names come from the user or the LLM; Qloo must resolve them.
"""

import asyncio

from ..qloo.client import QlooRun
from ..qloo.models import LookupResponse, SearchHit, SearchResponse
from ..schemas import CultureAnchor, EntityOut
from .resolve import name_matches

CULTURE_TYPES = ("urn:entity:movie", "urn:entity:tv_show", "urn:entity:artist")


def entity_out(hit: SearchHit, type_: str) -> EntityOut:
    return EntityOut(
        entity_id=hit.entity_id, name=hit.name, type=type_, year=hit.year, image_url=hit.image_url
    )


async def search_culture(run: QlooRun, query: str, take: int = 4) -> list[EntityOut]:
    """Picker search across films, shows and artists."""

    async def one(type_: str) -> list[EntityOut]:
        _, body = await run.get(
            "search", "/search", {"query": query, "types": type_, "take": str(take)}
        )
        return [
            entity_out(h, type_)
            for h in SearchResponse.model_validate(body).results
            if type_ in h.types
        ]

    hits = [e for group in await asyncio.gather(*(one(t) for t in CULTURE_TYPES)) for e in group]
    exact = [e for e in hits if name_matches(query, e.name)]
    return exact + [e for e in hits if e not in exact]


async def resolve_culture(
    run: QlooRun, names: list[tuple[str, str]]
) -> tuple[list[EntityOut], list[str]]:
    """Resolve (name, type) pairs. Unresolved names are dropped, never invented (P1)."""

    async def one(name: str, type_: str) -> EntityOut | None:
        _, body = await run.get("S1", "/search", {"query": name, "types": type_, "take": "5"})
        for hit in SearchResponse.model_validate(body).results:
            if type_ in hit.types and name_matches(name, hit.name):
                return entity_out(hit, type_)
        return None

    results = await asyncio.gather(*(one(n, t) for n, t in names))
    return [r for r in results if r], [n for (n, _), r in zip(names, results, strict=True) if not r]


async def lookup_culture(
    run: QlooRun, entity_ids: list[str]
) -> tuple[list[CultureAnchor], list[str]]:
    """S1 for a plan: confirm each anchor id is a real Qloo film, show or artist."""
    if not entity_ids:
        return [], []
    rid, body = await run.get("S1", "/entities", {"entity_ids": ",".join(entity_ids)})
    found: dict[str, CultureAnchor] = {}
    for e in LookupResponse.model_validate(body).results:
        type_ = next((t for t in CULTURE_TYPES if t in e.types or e.subtype == t), None)
        if type_:
            found[e.entity_id] = CultureAnchor(
                entity_id=e.entity_id, name=e.name, type=type_, image_url=e.image_url, result_id=rid
            )
    return [found[i] for i in entity_ids if i in found], [i for i in entity_ids if i not in found]
