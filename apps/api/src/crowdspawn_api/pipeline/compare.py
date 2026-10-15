"""S6: taste gap between the studio's previous game(s) and the target comp set."""

from ..qloo.client import QlooRun
from ..qloo.models import CompareResponse
from ..schemas import Gap

TAKE = 12


async def gap(run: QlooRun, previous_ids: list[str], comp_ids: list[str]) -> Gap:
    rid, body = await run.get(
        "S6",
        "/v2/analysis/compare",
        {
            "a.signal.interests.entities": ",".join(previous_ids),
            "b.signal.interests.entities": ",".join(comp_ids),
            "take": str(TAKE),
        },
    )
    r = CompareResponse.model_validate(body).results
    a = {t.name.lower(): t.name for t in r.a}
    b = {t.name.lower(): t.name for t in r.b}
    return Gap(
        shared=list(dict.fromkeys(t.name for t in r.tags))[:TAKE],
        target_only=[v for k, v in b.items() if k not in a][:TAKE],
        studio_only=[v for k, v in a.items() if k not in b][:TAKE],
        result_id=rid,
    )
