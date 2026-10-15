"""S1: resolve comp names to Qloo video game entities."""

import asyncio
import re
import unicodedata
from difflib import SequenceMatcher

from ..qloo.client import QlooRun
from ..qloo.models import LookupResponse, SearchHit, SearchResponse
from ..schemas import Comp, EntityOut, Suggestion

ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9"}
MATCH_THRESHOLD = 0.9


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    tokens = re.sub(r"[^a-z0-9]+", " ", s).split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    return " ".join(ROMAN.get(t, t) for t in tokens)


def name_matches(query: str, candidate: str) -> bool:
    a, b = normalize(query), normalize(candidate)
    return a == b or SequenceMatcher(None, a, b).ratio() >= MATCH_THRESHOLD


GAME = "urn:entity:videogame"


def _entity_out(hit: SearchHit) -> EntityOut:
    return EntityOut(
        entity_id=hit.entity_id, name=hit.name, type=GAME, year=hit.year, image_url=hit.image_url
    )


async def search_games(run: QlooRun, query: str, take: int = 8) -> list[EntityOut]:
    _, body = await run.get("search", "/search", {"query": query, "types": GAME, "take": str(take)})
    return [_entity_out(h) for h in SearchResponse.model_validate(body).results if GAME in h.types]


async def resolve_names(run: QlooRun, names: list[str]) -> tuple[list[Suggestion], list[str]]:
    """Resolve LLM- or user-typed names. Unresolved names are dropped, never invented (P1)."""

    async def one(name: str) -> Suggestion:
        _, body = await run.get("S1", "/search", {"query": name, "types": GAME, "take": "5"})
        for hit in SearchResponse.model_validate(body).results:
            if GAME in hit.types and name_matches(name, hit.name):
                return Suggestion(input_name=name, resolved=_entity_out(hit))
        return Suggestion(input_name=name, resolved=None)

    results = await asyncio.gather(*(one(n) for n in names))
    return [s for s in results if s.resolved], [s.input_name for s in results if not s.resolved]


async def lookup_comps(run: QlooRun, entity_ids: list[str]) -> tuple[list[Comp], list[str]]:
    """S1 for a plan: confirm each comp id is a real Qloo video game and fetch its name."""
    rid, body = await run.get("S1", "/entities", {"entity_ids": ",".join(entity_ids)})
    found = {
        e.entity_id: e
        for e in LookupResponse.model_validate(body).results
        if GAME in e.types or e.subtype == GAME
    }
    comps = [
        Comp(entity_id=i, name=found[i].name, image_url=found[i].image_url, result_id=rid)
        for i in entity_ids
        if i in found
    ]
    return comps, [i for i in entity_ids if i not in found]
