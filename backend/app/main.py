from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
import logging
import os

import redis
from sqlalchemy import text

from app.logging_config import configure_logging, refresh_log_level_from_db
from app.request_context import (
    REQUEST_ID_HEADER,
    clear_request_id,
    new_request_id,
    set_request_id,
)

configure_logging()

# Import celery_app FIRST so its broker/backend config (REDIS_URL) is registered
# as the current Celery app BEFORE any module imports tasks via @shared_task —
# otherwise the tasks bind to Celery's default amqp:// broker and publishes
# fail with "Connection refused".
from celery_app import celery_app, REDIS_URL  # noqa: F401, E402

from app.database import SessionLocal, engine, Base
from app.db_helpers import (
    authenticate_internal_request_with_body,
    clear_request_user_id,
    set_request_user_id,
)
from app.error_reporting import report_exception
from app.routes import api_router
from app.security.data_encryption import is_data_encryption_enabled
from app.services.category_instruction_lint import log_dangling_references

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


def _get_cors_origins() -> list[str]:
    """
    Determine allowed CORS origins.

    If CORS_ALLOW_ORIGINS is not set, APP_URL/FRONTEND_URL is used.
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS")
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if origins:
            return origins

    frontend_url = os.getenv("FRONTEND_URL") or os.getenv("APP_URL")
    if frontend_url:
        return [frontend_url]

    return ["http://localhost:3000"]


# Guarded dev helper (schema migrations are owned by Drizzle; prefer running migrations)
if _env_bool("AUTO_CREATE_TABLES", default=False):
    logger.warning("AUTO_CREATE_TABLES is enabled; creating tables via SQLAlchemy metadata.")
    Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    refresh_log_level_from_db(SessionLocal)
    # Hygiene only: warns when a category's categorization_instructions route
    # to a name the tree no longer has. One read-only query, and it swallows
    # its own failures -- see the module docstring for why this never blocks
    # a boot.
    log_dangling_references(SessionLocal)
    if not is_data_encryption_enabled():
        logger.error(
            "=" * 78 + "\n"
            "DATA_ENCRYPTION_KEY_CURRENT is not set. Sensitive fields (e.g. IBANs, "
            "account external IDs) will be stored in PLAINTEXT. This app hosts "
            "financial data — set DATA_ENCRYPTION_KEY_CURRENT (see deploy/install/"
            "install.sh or .env.example) before running in production.\n" + "=" * 78
        )
    yield


app = FastAPI(
    title="Syllogic API",
    description="API for Syllogic (personal finance management)",
    version="0.1.0",
    docs_url="/docs" if _env_bool("API_DOCS_ENABLED", default=False) else None,
    redoc_url="/redoc" if _env_bool("API_DOCS_ENABLED", default=False) else None,
    openapi_url="/openapi.json" if _env_bool("API_DOCS_ENABLED", default=False) else None,
    lifespan=_lifespan,
)


UNPROTECTED_API_PATHS = {"/api/health"}


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Threads a request id through this service's logs (see
    RequestIdLogFilter) and echoes it back in the response header, for
    every request -- including ones internal_auth_middleware short-circuits
    (health checks, CORS preflights, auth failures). Trusts the incoming
    header since it's only ever set by Caddy or the Next.js BFF, both
    inside the trust boundary; a caller sending a bogus one only pollutes
    their own request's log correlation, not anyone else's."""
    incoming = request.headers.get(REQUEST_ID_HEADER)
    request_id = incoming.strip() if incoming and incoming.strip() else new_request_id()
    # request.state (not just the contextvar) so it's still readable from
    # the exception_handler for a bare Exception, which Starlette runs in
    # its outermost ServerErrorMiddleware -- outside this middleware, after
    # the `finally` below has already reset the contextvar.
    request.state.request_id = request_id
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        clear_request_id(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.middleware("http")
async def internal_auth_middleware(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/") or path in UNPROTECTED_API_PATHS:
        return await call_next(request)

    # Throttled internally (see logging_config.REFRESH_INTERVAL_SECONDS), so this
    # is a no-op most requests; it exists so a log level saved in the Settings UI
    # propagates to every gunicorn worker without a restart. Best-effort: a
    # transient DB hiccup here must not turn every request into a 500 --
    # health checks and CORS preflights already bypass this via the early
    # return above, but authenticated /api/* traffic shouldn't fail on a
    # logging lookup either.
    try:
        refresh_log_level_from_db(SessionLocal)
    except Exception:
        logger.warning("Failed to refresh log level from DB", exc_info=True)

    path_with_query = path
    if request.url.query:
        path_with_query = f"{path_with_query}?{request.url.query}"

    try:
        body_bytes = await request.body()
        request_user_id = authenticate_internal_request_with_body(
            method=request.method,
            path_with_query=path_with_query,
            headers=request.headers,
            body_bytes=body_bytes,
        )
    except Exception as exc:
        if hasattr(exc, "status_code") and hasattr(exc, "detail"):
            return JSONResponse(
                status_code=getattr(exc, "status_code"),
                content={"detail": getattr(exc, "detail")},
            )
        logger.exception("Unexpected internal auth error")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal authentication failure."},
        )

    token = set_request_user_id(request_user_id)
    try:
        response = await call_next(request)
    finally:
        clear_request_user_id(token)

    return response


@app.exception_handler(Exception)
async def _handle_unhandled_exception(request: Request, exc: Exception):
    # FastAPI only calls this for exceptions nothing more specific caught
    # (HTTPException etc. are handled separately and never reach here), so
    # this is strictly additive: same response Starlette's default
    # ServerErrorMiddleware would have sent, plus the opt-in report.
    #
    # Registered handlers for a bare Exception run in Starlette's outermost
    # ServerErrorMiddleware, outside request_id_middleware -- by the time
    # we're here its `finally: clear_request_id()` has already reset the
    # contextvar, so read it back from request.state instead (set before
    # the contextvar in request_id_middleware, and unaffected by that
    # reset).
    request_id = getattr(request.state, "request_id", "-")
    await report_exception(exc, path=request.url.path, method=request.method, request_id=request_id)
    logger.exception("Unhandled exception")
    # request_id_middleware never gets to echo the header itself here --
    # call_next() raised instead of returning a response for it to stamp.
    return PlainTextResponse(
        "Internal Server Error", status_code=500, headers={REQUEST_ID_HEADER: request_id}
    )


# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/")
def root():
    payload = {"message": "Syllogic API"}
    if _env_bool("API_DOCS_ENABLED", default=False):
        payload["docs"] = "/docs"
    return payload


@app.get("/health")
def health():
    """Liveness only: does the process respond. See /health/ready for an
    actual dependency check."""
    return {"status": "healthy"}


@app.get("/health/ready")
def health_ready():
    """Readiness: can this instance actually serve traffic. Touches
    Postgres and Redis with a short timeout so the Compose healthcheck (and
    its restart policy) reflects a dead dependency instead of just the
    process being alive."""
    checks: dict[str, bool] = {}

    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            checks["database"] = True
        finally:
            db.close()
    except Exception:
        logger.warning("Readiness check: database unreachable", exc_info=True)
        checks["database"] = False

    try:
        redis_client = redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        redis_client.ping()
        checks["redis"] = True
    except Exception:
        logger.warning("Readiness check: redis unreachable", exc_info=True)
        checks["redis"] = False

    healthy = all(checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "healthy" if healthy else "unhealthy", "checks": checks},
    )
