"""Tests for the MCP verified-API-key cache.

Deliberately mock-backed rather than database-backed: what's under test is
how often `validate_api_key` reaches for the database and for bcrypt, which
is easiest to assert by counting calls.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.mcp import auth as auth_module
from app.mcp.auth import invalidate_api_key_cache, validate_api_key


VALID_KEY = "pf_abcdef12_secret_value"


class _FakeQuery:
    """Stands in for `db.query(ApiKey).filter(...)`.

    `validate_api_key` runs the legacy-hash lookup (`.first()`) before the
    prefix lookup (`.all()`), so one object can serve both.
    """

    def __init__(self, first_result, all_result):
        self._first = first_result
        self._all = all_result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._all


class _FakeSessionFactory:
    """Counts how many sessions `validate_api_key` opens."""

    def __init__(self, record):
        self.record = record
        self.session_count = 0

    def __call__(self):
        self.session_count += 1
        session = MagicMock()
        session.query.return_value = _FakeQuery(
            first_result=None,
            all_result=[self.record] if self.record else [],
        )
        return session


def _clock_at(moment):
    """A `datetime` stand-in whose `now()` is fixed at `moment`.

    A subclass rather than a MagicMock so that instances are still real
    datetimes and comparisons against them behave normally.
    """

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment if tz else moment.replace(tzinfo=None)

    return _FrozenDatetime


def _make_record(expires_at=None, user_id="user_123"):
    record = MagicMock()
    record.id = uuid.uuid4()
    record.user_id = user_id
    record.key_hash = "$2b$12$notarealhash"
    record.expires_at = expires_at
    record.last_used_at = None
    return record


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_api_key_cache()
    yield
    invalidate_api_key_cache()


class _FakeEngine:
    """Stands in for the module-level engine.

    Two paths run through it on a cache hit: `begin()` writes
    `last_used_at`, and `connect()` re-reads the row to confirm the key has
    not been revoked. Both are counted so tests can assert how much the
    cached path still costs.
    """

    def __init__(self):
        self.begin_calls = 0
        self.connect_calls = 0
        # What `SELECT expires_at FROM api_keys WHERE id = :id` returns.
        # None stands for "no such row", i.e. the key was revoked.
        self.row = (None,)
        self.begin_error = None
        self.connect_error = None

    @contextlib.contextmanager
    def begin(self):
        self.begin_calls += 1
        if self.begin_error:
            raise self.begin_error
        yield MagicMock()

    @contextlib.contextmanager
    def connect(self):
        self.connect_calls += 1
        if self.connect_error:
            raise self.connect_error
        conn = MagicMock()
        conn.execute.return_value.first.return_value = self.row
        yield conn


@pytest.fixture
def fake_engine():
    """Replaces the module-level engine so database work is counted instead
    of executed."""
    engine = _FakeEngine()
    with patch.object(auth_module, "engine", engine):
        yield engine


class TestCacheHits:
    def test_repeat_calls_do_not_reopen_the_database(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            first = validate_api_key(VALID_KEY)
            rest = [validate_api_key(VALID_KEY) for _ in range(9)]

        assert first == "user_123"
        assert rest == ["user_123"] * 9
        assert factory.session_count == 1

    def test_bcrypt_runs_once_across_many_calls(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True) as verify,
        ):
            for _ in range(10):
                validate_api_key(VALID_KEY)

        assert verify.call_count == 1

    def test_distinct_keys_are_cached_separately(self, fake_engine):
        record_a = _make_record(user_id="user_a")
        record_b = _make_record(user_id="user_b")
        factory = _FakeSessionFactory(record_a)

        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            assert validate_api_key("pf_aaaaaaaa_one") == "user_a"
            factory.record = record_b
            assert validate_api_key("pf_bbbbbbbb_two") == "user_b"
            # Both still resolve to their own user from cache.
            assert validate_api_key("pf_aaaaaaaa_one") == "user_a"

        assert factory.session_count == 2


class TestCacheExpiry:
    def test_entry_is_reverified_after_ttl(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            validate_api_key(VALID_KEY)
            assert factory.session_count == 1

            # Monotonic time only moves forward, so the fake clock has to be
            # anchored to the real one rather than starting from zero.
            past_ttl = auth_module.time.monotonic() + auth_module._CACHE_TTL_SECONDS + 1
            with patch.object(auth_module.time, "monotonic", return_value=past_ttl):
                validate_api_key(VALID_KEY)

        assert factory.session_count == 2

    def test_key_expiring_mid_ttl_is_rejected_without_reverifying(self, fake_engine):
        # Valid when first verified, lapsed by the time it is used again.
        # The lapse is produced by moving the clock rather than by sleeping
        # past a short real expiry: a real-time window small enough to keep
        # the suite fast is also small enough for a loaded machine to blow
        # through during the first call, which made this test fail at random.
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
        factory = _FakeSessionFactory(_make_record(expires_at=expires_at))
        fake_engine.row = (expires_at,)

        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            assert validate_api_key(VALID_KEY) == "user_123"
            assert factory.session_count == 1

            # Still inside the cache TTL, but past the key's own expiry.
            with patch.object(
                auth_module, "datetime", _clock_at(expires_at + timedelta(seconds=1))
            ):
                assert validate_api_key(VALID_KEY) is None

        # Rejected without a second bcrypt comparison: the key was never
        # re-verified, only re-read.
        assert factory.session_count == 1

    def test_naive_expires_at_is_treated_as_utc(self):
        past_naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        future_naive = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
        assert auth_module._is_expired(past_naive) is True
        assert auth_module._is_expired(future_naive) is False
        assert auth_module._is_expired(None) is False


class TestNegativeCaching:
    def test_unknown_key_is_cached(self, fake_engine):
        factory = _FakeSessionFactory(None)
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=False) as verify,
        ):
            results = [validate_api_key("pf_badbadba_nope") for _ in range(5)]

        assert results == [None] * 5
        assert factory.session_count == 1
        assert verify.call_count == 0  # no candidates to compare against

    def test_non_pf_key_never_touches_the_database(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with patch.object(auth_module, "SessionLocal", factory):
            assert validate_api_key("not-a-syllogic-key") is None
            assert validate_api_key("") is None

        assert factory.session_count == 0


class TestLastUsedThrottling:
    def test_last_used_is_not_rewritten_within_the_interval(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            for _ in range(10):
                validate_api_key(VALID_KEY)

        # The first call writes through the session it already had open; the
        # nine cached calls must not produce their own writes.
        assert fake_engine.begin_calls == 0

    def test_last_used_is_rewritten_after_the_interval(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            validate_api_key(VALID_KEY)

            # Past the last-used interval but still inside the cache TTL, so
            # the key resolves from cache and only the timestamp is refreshed.
            with (
                patch.object(
                    auth_module,
                    "_LAST_USED_MIN_INTERVAL_SECONDS",
                    0,
                ),
                patch.object(auth_module, "_CACHE_TTL_SECONDS", 3600),
            ):
                validate_api_key(VALID_KEY)

        assert factory.session_count == 1
        assert fake_engine.begin_calls == 1

    def test_failed_last_used_write_does_not_fail_auth(self, fake_engine):
        fake_engine.begin_error = RuntimeError("database gone")
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            validate_api_key(VALID_KEY)
            with (
                patch.object(auth_module, "_LAST_USED_MIN_INTERVAL_SECONDS", 0),
                patch.object(auth_module, "_CACHE_TTL_SECONDS", 3600),
            ):
                assert validate_api_key(VALID_KEY) == "user_123"


class TestInvalidation:
    def test_invalidating_one_key_forces_reverification(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            validate_api_key(VALID_KEY)
            invalidate_api_key_cache(VALID_KEY)
            validate_api_key(VALID_KEY)

        assert factory.session_count == 2

    def test_invalidating_one_key_leaves_others_cached(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            validate_api_key("pf_aaaaaaaa_one")
            validate_api_key("pf_bbbbbbbb_two")
            assert factory.session_count == 2

            invalidate_api_key_cache("pf_aaaaaaaa_one")
            validate_api_key("pf_bbbbbbbb_two")

        assert factory.session_count == 2


class TestCacheBounds:
    def test_cache_does_not_grow_without_limit(self, fake_engine):
        factory = _FakeSessionFactory(None)
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=False),
        ):
            for i in range(auth_module._CACHE_MAX_ENTRIES + 200):
                validate_api_key(f"pf_{i:08d}_junk")

        assert len(auth_module._cache) <= auth_module._CACHE_MAX_ENTRIES


class TestRevocation:
    """Deleting a key must stop it working now, not at the end of the TTL.

    The frontend deletes the row; the MCP server is a separate process with
    its own cache, so nothing can invalidate that cache remotely. Re-reading
    the row on each cached call is what closes the gap.
    """

    def test_revoked_key_is_rejected_on_the_next_call(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            assert validate_api_key(VALID_KEY) == "user_123"

            fake_engine.row = None  # row deleted
            assert validate_api_key(VALID_KEY) is None

        # And the stale entry is gone rather than waiting out its TTL.
        assert auth_module._cache_digest(VALID_KEY) not in auth_module._cache

    def test_cached_calls_re_read_the_row(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            for _ in range(5):
                validate_api_key(VALID_KEY)

        # One uncached verification plus four cached calls, each confirming
        # the key still exists.
        assert factory.session_count == 1
        assert fake_engine.connect_calls == 4

    def test_check_interval_trades_lag_for_lookups(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
            patch.object(auth_module, "_REVOCATION_CHECK_INTERVAL_SECONDS", 3600),
        ):
            assert validate_api_key(VALID_KEY) == "user_123"
            fake_engine.row = None
            # Inside the interval the revocation is not noticed -- which is
            # exactly what the setting buys, and why it defaults to 0.
            assert validate_api_key(VALID_KEY) == "user_123"

        # The initial verification counts as a confirmation, so inside the
        # interval no extra lookup happens at all.
        assert fake_engine.connect_calls == 0

    def test_failed_liveness_lookup_denies(self, fake_engine):
        factory = _FakeSessionFactory(_make_record())
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            assert validate_api_key(VALID_KEY) == "user_123"
            fake_engine.connect_error = RuntimeError("database gone")
            assert validate_api_key(VALID_KEY) is None

    def test_shortened_expiry_is_picked_up_from_the_row(self, fake_engine):
        factory = _FakeSessionFactory(_make_record(expires_at=None))
        with (
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            assert validate_api_key(VALID_KEY) == "user_123"
            fake_engine.row = (datetime.now(timezone.utc) - timedelta(seconds=1),)
            assert validate_api_key(VALID_KEY) is None


class TestAuthFailureLogging:
    """Rejections are the only signal that someone is guessing keys."""

    def test_unknown_key_is_logged(self, fake_engine, caplog):
        factory = _FakeSessionFactory(None)
        with (
            caplog.at_level(logging.WARNING, logger="app.mcp.auth"),
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=False),
        ):
            validate_api_key("pf_badbadba_nope")
            validate_api_key("pf_badbadba_nope")

        reasons = [r.getMessage() for r in caplog.records]
        assert any("reason=unknown_key " in message for message in reasons)
        assert any("reason=unknown_key_cached" in message for message in reasons)

    def test_revoked_key_is_logged(self, fake_engine, caplog):
        factory = _FakeSessionFactory(_make_record())
        with (
            caplog.at_level(logging.WARNING, logger="app.mcp.auth"),
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=True),
        ):
            validate_api_key(VALID_KEY)
            fake_engine.row = None
            validate_api_key(VALID_KEY)

        assert any("reason=revoked" in r.getMessage() for r in caplog.records)

    def test_malformed_key_is_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="app.mcp.auth"):
            assert validate_api_key("not-a-syllogic-key") is None

        assert any("reason=malformed" in r.getMessage() for r in caplog.records)

    def test_logs_never_contain_the_key_or_its_prefix(self, fake_engine, caplog):
        factory = _FakeSessionFactory(None)
        with (
            caplog.at_level(logging.WARNING, logger="app.mcp.auth"),
            patch.object(auth_module, "SessionLocal", factory),
            patch.object(auth_module, "verify_api_key", return_value=False),
        ):
            validate_api_key(VALID_KEY)

        text = "\n".join(r.getMessage() for r in caplog.records)
        assert text  # something was logged
        assert VALID_KEY not in text
        # The `pf_` prefix is eight characters of the real secret.
        assert VALID_KEY[:11] not in text
