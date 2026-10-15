"""Typed errors rendered as RFC 7807 problem responses."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    status = 500
    code = "internal_error"
    title = "Internal error"

    def __init__(self, detail: str = "", *, code: str | None = None, status: int | None = None):
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        if code:
            self.code = code
        if status:
            self.status = status

    def problem(self) -> dict[str, object]:
        return {
            "type": f"https://crowdspawn.dev/problems/{self.code}",
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
        }


class QlooError(AppError):
    """Any Qloo failure. Plans fail closed on these."""

    status = 502
    code = "qloo_unavailable"
    title = "Qloo request failed"


class QlooUnconfigured(QlooError):
    status = 503
    code = "qloo_unconfigured"
    title = "Qloo API key is not configured"


class QlooAuthError(QlooError):
    code = "qloo_auth"
    title = "Qloo rejected the API key"


class QlooRateLimited(QlooError):
    status = 503
    code = "qloo_rate_limited"
    title = "Qloo rate limit hit"


class QlooBudgetExceeded(QlooError):
    status = 503
    code = "qloo_budget_exceeded"
    title = "Per-run Qloo call budget exceeded"


class QlooFilterIgnored(QlooError):
    code = "qloo_filter_ignored"
    title = "Qloo response did not reflect the requested filters"


class NotFound(AppError):
    status = 404
    code = "plan_not_found"
    title = "Not found"


class RateLimited(AppError):
    status = 429
    code = "rate_limited"
    title = "Too many plans from this address; try again later"


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(
        exc.problem(), status_code=exc.status, media_type="application/problem+json"
    )


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    detail = "; ".join(f"{'.'.join(map(str, e['loc'][1:]))}: {e['msg']}" for e in errors)
    return JSONResponse(
        {
            "type": "https://crowdspawn.dev/problems/validation_error",
            "title": "Invalid input",
            "status": 422,
            "detail": detail,
            "code": "validation_error",
            "errors": errors,
        },
        status_code=422,
        media_type="application/problem+json",
    )
