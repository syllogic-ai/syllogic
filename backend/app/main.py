from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from app.database import engine, Base
from app.db_helpers import (
    authenticate_internal_request_from_headers,
    clear_request_user_id,
    set_request_user_id,
)
from app.routes import api_router

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

app = FastAPI(
    title="Syllogic API",
    description="API for Syllogic (personal finance management)",
    version="0.1.0",
    docs_url="/docs" if _env_bool("API_DOCS_ENABLED", default=False) else None,
    redoc_url="/redoc" if _env_bool("API_DOCS_ENABLED", default=False) else None,
    openapi_url="/openapi.json" if _env_bool("API_DOCS_ENABLED", default=False) else None,
)


UNPROTECTED_API_PATHS = {"/api/health"}


@app.middleware("http")
async def internal_auth_middleware(request: Request, call_next):
    path = request.url.path
    if (
        request.method == "OPTIONS"
        or not path.startswith("/api/")
        or path in UNPROTECTED_API_PATHS
    ):
        return await call_next(request)

    path_with_query = path
    if request.url.query:
        path_with_query = f"{path_with_query}?{request.url.query}"

    try:
        request_user_id = authenticate_internal_request_from_headers(
            method=request.method,
            path_with_query=path_with_query,
            headers=request.headers,
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
    return {"status": "healthy"}
