"""
Database configuration for PostgreSQL using SQLAlchemy.
This mirrors the Drizzle schema.ts structure from the frontend.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pydantic_settings import BaseSettings
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


def _is_production_environment() -> bool:
    production_markers = {"production", "prod", "1", "true", "yes"}
    for env_var in (
        "NODE_ENV",
        "ENVIRONMENT",
        "APP_ENV",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_ENVIRONMENT_NAME",
    ):
        value = os.getenv(env_var, "").strip().lower()
        if value in production_markers:
            return True
    return False


def _database_url_requires_ssl(database_url: str) -> bool:
    lowered = database_url.lower()
    return (
        "ssl=true" in lowered
        or "sslmode=require" in lowered
        or "sslmode=verify-ca" in lowered
        or "sslmode=verify-full" in lowered
    )


def _should_enforce_database_ssl(database_url: str) -> bool:
    # For local single-host Docker deployments, the database is often reachable only
    # on a private bridge network without TLS enabled.
    # Enforce TLS for all non-local hosts.
    local_hosts = {"localhost", "127.0.0.1", "postgres", "db"}
    hostname = (urlparse(database_url).hostname or "").lower()
    return hostname not in local_hosts


class Settings(BaseSettings):
    """
    Database settings. Defaults to PostgreSQL.
    SQLite support has been removed - PostgreSQL is required.
    """
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://financeuser:financepass@localhost:5433/finance_db"
    )

    class Config:
        env_file = ".env"
        extra = "ignore"  # Allow extra fields in .env file


settings = Settings()

# Configure database URL - ensure PostgreSQL format
db_url = settings.database_url
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Validate that we're using PostgreSQL (SQLite no longer supported)
if db_url.startswith("sqlite"):
    raise ValueError(
        "SQLite is no longer supported. Please use PostgreSQL. "
        "Set DATABASE_URL to a PostgreSQL connection string, e.g.: "
        "postgresql+psycopg://user:password@localhost:5432/finance_db"
    )

if _is_production_environment() and _should_enforce_database_ssl(db_url) and not _database_url_requires_ssl(db_url):
    raise ValueError(
        "Production DATABASE_URL must require TLS. "
        "Use one of: '?sslmode=require', '?sslmode=verify-ca', '?sslmode=verify-full', or '?ssl=true'."
    )

# Create engine with PostgreSQL-specific settings
engine = create_engine(
    db_url,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,
    max_overflow=20,
    echo=False  # Set to True for SQL query logging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    Dependency for FastAPI to get database session.
    Yields a database session and ensures it's closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
