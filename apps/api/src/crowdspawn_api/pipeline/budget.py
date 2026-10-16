"""S7: deterministic budget split, proportional to spawn score x confidence weight. No Qloo, no LLM."""

from ..schemas import City

CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}


def largest_remainder(weights: list[float], total_units: int) -> list[int]:
    """Split integer units in proportion to weights so the parts sum exactly to total_units."""
    if sum(weights) <= 0:
        weights = [1.0] * len(weights)
    s = sum(weights)
    raw = [w / s * total_units for w in weights]
    floors = [int(x) for x in raw]
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - floors[i]), i))
    for i in order[: total_units - sum(floors)]:
        floors[i] += 1
    return floors


def split_budget(cities: list[City], budget_usd: float | None) -> list[City]:
    """Only over-indexing cities (score > 1) get budget; if none do, all cities share it."""
    eligible = [c for c in cities if c.score > 1] or cities
    if not eligible:
        return cities
    weights = [c.score * CONFIDENCE_WEIGHT[c.confidence] for c in eligible]
    shares = largest_remainder(weights, 10_000)  # hundredths of a percent
    cents = largest_remainder(weights, round(budget_usd * 100)) if budget_usd else None
    by_id = {c.region_id: i for i, c in enumerate(eligible)}
    out = []
    for c in cities:
        i = by_id.get(c.region_id)
        out.append(
            c.model_copy(
                update={
                    "budget_share": shares[i] / 100 if i is not None else 0.0,
                    "budget_usd": (cents[i] / 100 if i is not None else 0.0) if cents else None,
                }
            )
        )
    return out
