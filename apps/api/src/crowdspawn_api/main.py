import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from .errors import AppError, app_error_handler, validation_error_handler
from .llm.registry import build_provider
from .pipeline import scout
from .pipeline.orchestrator import Deps
from .qloo.client import QlooClient
from .routes import health, v1
from .settings import Settings, get_settings
from .storage import Store

request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


async def _warm_scout(qloo: QlooClient) -> None:
    """Fill the week-long cache behind /v1/scout/activity; cached readings cost no calls."""
    try:
        await scout.activity(qloo.run(max_calls=3 * len(scout.scout_points())))
    except Exception:  # best effort: the endpoint fetches on demand anyway
        logging.getLogger(__name__).warning("scout warm-up failed", exc_info=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(logging.Formatter("%(levelname)s [%(request_id)s] %(name)s: %(message)s"))
    logging.basicConfig(level=s.log_level.upper(), handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(
        logging.WARNING
    )  # its URLs never carry keys, but keep quiet

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = await Store.open(s.db_file)
        qloo = QlooClient(s, store)
        llm = build_provider(s)
        app.state.deps = Deps(settings=s, store=store, qloo=qloo, llm=llm)
        warm = None
        if qloo.configured and s.app_env != "test":
            warm = asyncio.create_task(_warm_scout(qloo))  # first map visit is instant
        yield
        if warm and not warm.done():
            warm.cancel()
        await qloo.aclose()
        if llm:
            await llm.aclose()
        await store.close()

    app = FastAPI(title="Crowdspawn API", version=health.VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    @app.middleware("http")
    async def add_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request_id.set(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
