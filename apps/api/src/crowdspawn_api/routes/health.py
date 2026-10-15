from typing import Literal

from fastapi import APIRouter, Request

from ..errors import QlooError
from ..llm.registry import model_name
from ..pipeline.orchestrator import Deps
from ..schemas import Health, LLMStatus

router = APIRouter()
VERSION = "0.1.0"


@router.get("/health", response_model=Health)
async def health(request: Request) -> Health:
    d: Deps = request.app.state.deps
    qloo: Literal["ok", "unconfigured", "error"] = "unconfigured"
    if d.qloo.configured:
        try:  # one trivial search, cached for QLOO_CACHE_TTL_SECONDS
            await d.qloo.run(max_calls=1).get(
                "health",
                "/search",
                {"query": "Minecraft", "types": "urn:entity:videogame", "take": "1"},
            )
            qloo = "ok"
        except QlooError:
            qloo = "error"
    llm = LLMStatus(
        provider=d.settings.llm_provider,
        model=model_name(d.settings),
        status="configured" if d.llm else "unconfigured",
    )
    return Health(status="ok" if qloo == "ok" else "degraded", qloo=qloo, llm=llm, version=VERSION)
