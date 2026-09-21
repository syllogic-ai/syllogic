"""
Shared pytest fixtures for the backend test suite.

Every test gets a clean database: after each test, every application table
is truncated. This is deliberately *not* the classic "wrap the test in a
transaction and roll it back" recipe -- this codebase's routes/services
each open their own `SessionLocal()` and commit independently (there is no
single request-scoped session to hook), including from code the fixture
never sees (Celery tasks, nested service calls). Rebinding `SessionLocal`
onto one shared connection with per-Session SAVEPOINTs was tried and
discarded: a `Session.rollback()` call on a session that hasn't itself
started a transaction falls through to the shared connection and rolls
back *everything*, including other sessions' already-committed work --
exactly the kind of defensive `db.rollback()` calls this test suite already
does routinely (see e.g. test_report_tasks.py). Truncating after the fact
sidesteps that class of bug entirely: every `SessionLocal()` call anywhere
keeps behaving exactly like it does in production.

DATABASE_URL must point at a disposable database -- CI runs this against a
fresh Postgres service container; locally it defaults to `finance_test` on
the docker-compose Postgres, never to `finance_db` (see `_resolve_database_url`
below, and `scripts/test-backend.sh`, which provisions that database).
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import time
from urllib.parse import urlparse

# Ensure the backend/ directory is importable when pytest is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Every test truncates every table, so the default target must never be the
# database the dev stack (or anything else) actually keeps data in.
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://financeuser:financepass@localhost:5433/finance_test"
)

# Databases this suite refuses to run against, because wiping them costs real
# work. Override deliberately with ALLOW_DESTRUCTIVE_TEST_DB=1 if you really
# do want a run to truncate one of them.
PROTECTED_DATABASE_NAMES = {"finance_db"}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}

_SETUP_HINT = "Run scripts/test-backend.sh (add --reset to rebuild the schema from scratch)."


def _resolve_database_url() -> str:
    """Pick the database this run truncates, and refuse the dangerous ones.

    Precedence: TEST_DATABASE_URL, then DATABASE_URL, then the compose-local
    `finance_test` default. The result is written back to DATABASE_URL so that
    `app.database` -- which builds its engine at import time -- picks it up.
    """
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        url = DEFAULT_TEST_DATABASE_URL

    db_name = urlparse(url).path.lstrip("/")
    # The guard protects a developer's dev database. In CI the whole Postgres
    # is a throwaway service container, and it is named finance_db there.
    allowed = os.environ.get("CI") or os.environ.get("ALLOW_DESTRUCTIVE_TEST_DB") in {
        "1",
        "true",
        "yes",
    }
    if db_name in PROTECTED_DATABASE_NAMES and not allowed:
        raise RuntimeError(
            f"Refusing to run the test suite against '{db_name}': every test truncates "
            "every table, so this would wipe it.\n"
            f"{_SETUP_HINT}\n"
            "Or point TEST_DATABASE_URL at a scratch database yourself. Set "
            "ALLOW_DESTRUCTIVE_TEST_DB=1 only if wiping it is genuinely what you want."
        )

    os.environ["DATABASE_URL"] = url
    return url


def _can_connect(url: str) -> bool:
    import sqlalchemy

    try:
        probe = sqlalchemy.create_engine(url, connect_args={"connect_timeout": 2})
        with probe.connect():
            return True
    except Exception:
        return False
    finally:
        try:
            probe.dispose()
        except Exception:
            pass


def _ensure_database_reachable(url: str) -> None:
    """Start the compose Postgres/Redis if the database is not answering.

    The single most common reason this suite "fails sometimes" locally is that
    the `finance_db` container is simply stopped, which turns every
    database-backed test into a connection error. Starting it is idempotent,
    so just do it rather than making it the developer's job to notice.
    """
    if _can_connect(url):
        return

    host = (urlparse(url).hostname or "").lower()
    if host not in _LOCAL_HOSTS or os.environ.get("CI"):
        raise RuntimeError(f"Cannot reach the test database at {url}.\n{_SETUP_HINT}")

    print(f"[conftest] {url} is not answering; starting compose services db + redis", flush=True)
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "db", "redis"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"") or b""
        raise RuntimeError(
            f"Cannot reach the test database at {url}, and 'docker compose up -d db redis' "
            f"failed: {detail.decode(errors='replace').strip() or exc}\n{_SETUP_HINT}"
        ) from exc

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if _can_connect(url):
            print("[conftest] database is up", flush=True)
            return
        time.sleep(1)

    raise RuntimeError(
        f"Started the compose services but {url} still is not answering after 60s.\n{_SETUP_HINT}"
    )


def _set_test_env() -> None:
    """Deterministic encryption keys so blind_index/encrypted fields work in tests."""
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ.setdefault("DATA_ENCRYPTION_KEY_CURRENT", key)
    os.environ.setdefault("DATA_ENCRYPTION_KEY_ID", "k-test-conftest")
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)
    # The broker-trade import runs a yfinance + FX backfill in production to
    # populate historical HoldingValuation / AccountBalance rows. Disable it
    # by default in tests; tests that exercise backfill set it explicitly.
    os.environ.setdefault("BROKER_BACKFILL_ENABLED", "0")


_set_test_env()
_DATABASE_URL = _resolve_database_url()
_ensure_database_reachable(_DATABASE_URL)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.mcp.auth import invalidate_api_key_cache  # noqa: E402
from app.security.data_encryption import reset_encryption_config_cache  # noqa: E402
import app.models  # noqa: E402, F401 -- registers every table on Base.metadata


reset_encryption_config_cache()

_ALL_TABLES = [table.name for table in Base.metadata.sorted_tables]


def _assert_schema_matches_models() -> None:
    """Fail the whole run, up front, when the test database is out of date.

    A stale test database does not fail cleanly: the first query against a
    missing column raises inside the test, and then the post-test TRUNCATE
    raises too, so a single missing migration shows up as dozens of unrelated
    failures and errors scattered across the suite -- and, because the
    truncation never runs, state leaks into whatever runs next and the damage
    varies with test order. Check once instead.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )
        ).all()

    live: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        live.setdefault(table_name, set()).add(column_name)

    problems = []
    for table in Base.metadata.sorted_tables:
        live_columns = live.get(table.name)
        if live_columns is None:
            problems.append(f"table '{table.name}' is missing")
            continue
        missing = sorted(set(table.columns.keys()) - live_columns)
        if missing:
            problems.append(f"table '{table.name}' is missing column(s): {', '.join(missing)}")

    if problems:
        listed = "\n  - ".join(problems)
        raise RuntimeError(
            f"The test database ({_DATABASE_URL}) does not match app/models.py:\n"
            f"  - {listed}\n"
            f"{_SETUP_HINT}"
        )


_assert_schema_matches_models()


@pytest.fixture(autouse=True)
def _clean_db():
    """Truncate every application table after each test so state never
    leaks between tests, regardless of how many sessions/commits the test
    (or the code it calls) used."""
    try:
        yield
    finally:
        # The MCP auth cache is process-local, so truncating api_keys isn't
        # enough on its own: a key verified in one test would keep resolving
        # in the next one, against a row that no longer exists.
        invalidate_api_key_cache()
        if not _ALL_TABLES:
            return
        with engine.begin() as conn:
            # If a test (or a fixture/helper it calls) leaked a connection
            # holding a transaction open, TRUNCATE would otherwise hang
            # forever waiting on its lock and silently wedge the whole
            # suite. Fail fast and name the blocker instead.
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            quoted = ", ".join(f'"{name}"' for name in _ALL_TABLES)
            try:
                conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
            except Exception as exc:
                # Only a 55P03 is actually the leaked-transaction case. Reporting
                # every failure as a lock timeout buried a stale test schema
                # behind a diagnosis that had nothing to do with it.
                if getattr(getattr(exc, "orig", None), "sqlstate", None) == "55P03":
                    raise RuntimeError(
                        "Post-test TRUNCATE timed out waiting on a lock -- a "
                        "previous test likely leaked an open DB session/transaction. "
                        "Check pg_stat_activity for 'idle in transaction' connections."
                    ) from exc
                raise RuntimeError(f"Post-test TRUNCATE failed: {exc}") from exc


@pytest.fixture
def db_session():
    """Yield a SQLAlchemy session; close on teardown. Actual cleanup happens
    via the `_clean_db` truncation fixture above, not a rollback -- code
    under test may have committed through other sessions this fixture never
    sees."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
