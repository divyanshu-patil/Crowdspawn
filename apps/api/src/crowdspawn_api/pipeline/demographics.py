"""S4: audience age and gender skew (over/under-index vs average, per Qloo)."""

from statistics import fmean

from ..errors import QlooFilterIgnored
from ..qloo.client import QlooRun
from ..qloo.models import DemographicsInsights
from ..schemas import Audience, Band, GenderSkew

AGE_LABELS = {
    "24_and_younger": "24 and under",
    "25_to_29": "25-29",
    "30_to_34": "30-34",
    "35_to_44": "35-44",
    "45_to_54": "45-54",
    "55_and_older": "55+",
}


async def audience(run: QlooRun, signal: list[str]) -> Audience:
    rid, body = await run.get(
        "S4",
        "/v2/insights",
        {"filter.type": "urn:demographics", "signal.interests.entities": ",".join(signal)},
    )
    rows = DemographicsInsights.model_validate(body).results.demographics
    if not rows:
        raise QlooFilterIgnored("Demographics response was empty")

    def avg(field: str, key: str) -> float:
        vals = [getattr(r.query, field)[key] for r in rows if key in getattr(r.query, field)]
        return round(fmean(vals), 3) if vals else 0.0

    return Audience(
        age=[Band(band=label, index=avg("age", key)) for key, label in AGE_LABELS.items()],
        gender=[GenderSkew(label=g, index=avg("gender", g)) for g in ("male", "female")],
        result_id=rid,
    )
