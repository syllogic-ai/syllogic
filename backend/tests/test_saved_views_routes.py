"""Tests for /api/saved-views routes.

Covers the code-review fixes for the saved-views feature:
  - a filter list longer than max_length is rejected (422)
  - exceeding the per-user saved-view cap returns 409
  - a corrupt Redis blob yields [] from list AND is preserved at a side key
  - a stored entry missing a required field is skipped, valid entries remain

Redis is faked in-memory (no real Redis dependency, no external service) by
monkeypatching `app.routes.saved_views.get_redis` — the module always calls
that function rather than holding a client reference at import time, so
this is a drop-in replacement. The fake implements just enough of the
get/set/pipeline(WATCH/MULTI/EXEC) surface that `_atomic_mutate` exercises,
including real WATCH semantics: every key carries a version counter bumped
on write, `FakePipeline.watch()` snapshots that version, and `execute()`
raises `redis.WatchError` if the watched key's version moved since — so the
retry/409 branches in `_atomic_mutate` are genuinely exercised rather than
inferred.

Run with:
    cd backend && .venv/bin/pytest tests/test_saved_views_routes.py -v
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid

import redis

# Ensure backend/ is importable when pytest is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-saved-views"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)
    os.environ.setdefault("INTERNAL_AUTH_SECRET", "test-internal-secret")


_set_test_env()

INTERNAL_AUTH_SECRET = os.environ["INTERNAL_AUTH_SECRET"]

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db_helpers import get_user_id  # noqa: E402
from app.main import app  # noqa: E402
from app.routes import saved_views  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory fake Redis — just enough of the client + pipeline surface for
# `_atomic_mutate` (WATCH/MULTI/EXEC) and `_load`/`_parse_blob` (GET/SET).
# ---------------------------------------------------------------------------


class FakeRedis:
    """In-memory fake with real per-key WATCH versioning.

    Every `set()`/`delete()` bumps a per-key version counter. `FakePipeline`
    snapshots that counter on `watch()` and `execute()` fails with
    `redis.WatchError` if the counter moved — i.e. some other write touched
    the key — since the watch was taken. This mirrors real Redis optimistic
    locking closely enough for `_atomic_mutate`'s retry loop to be tested
    for real instead of assumed to work.

    `on_watch`, if set, is invoked with the watched key every time
    `watch()` is called — tests use this as a hook to simulate a
    concurrent writer sneaking in between WATCH and EXEC.
    """

    def __init__(self):
        self.store: dict[str, str] = {}
        self.versions: dict[str, int] = {}
        self.on_watch = None

    def _bump(self, key: str) -> None:
        self.versions[key] = self.versions.get(key, 0) + 1

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str):
        self.store[key] = value
        self._bump(key)
        return True

    def delete(self, key: str):
        existed = key in self.store
        self.store.pop(key, None)
        self._bump(key)
        return 1 if existed else 0

    def pipeline(self, transaction: bool = True):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, client: FakeRedis):
        self._client = client
        self._queued: list[tuple[str, str]] = []
        self._in_multi = False
        self._watched: dict[str, int] = {}

    def watch(self, key: str):
        # Snapshot the key's version so execute() can detect a change.
        self._watched[key] = self._client.versions.get(key, 0)
        if self._client.on_watch is not None:
            self._client.on_watch(key)

    def get(self, key: str):
        # Pre-MULTI, redis-py pipeline commands execute immediately.
        return self._client.get(key)

    def multi(self):
        self._in_multi = True

    def set(self, key: str, value: str):
        if self._in_multi:
            self._queued.append((key, value))
        else:
            self._client.set(key, value)

    def execute(self):
        for key, expected_version in self._watched.items():
            if self._client.versions.get(key, 0) != expected_version:
                self._queued = []
                raise redis.WatchError(f"watched key changed: {key}")
        for key, value in self._queued:
            self._client.set(key, value)
        results = [True] * len(self._queued)
        self._queued = []
        return results

    def reset(self):
        self._queued = []
        self._in_multi = False
        self._watched = {}


@pytest.fixture
def fake_redis(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(saved_views, "get_redis", lambda: client)
    return client


# ---------------------------------------------------------------------------
# Signed-request test client (mirrors tests/test_report_routes.py conventions)
# ---------------------------------------------------------------------------


def _signed_headers(method: str, path_with_query: str, user_id: str) -> dict:
    timestamp = str(int(time.time()))
    payload = "\n".join([method.upper(), path_with_query, user_id, timestamp])
    signature = hmac.new(
        INTERNAL_AUTH_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "x-syllogic-user-id": user_id,
        "x-syllogic-timestamp": timestamp,
        "x-syllogic-signature": signature,
    }


class _SigningClient:
    """Wraps TestClient to attach signed internal-auth headers (required by
    app.main's internal_auth_middleware) alongside overriding get_user_id
    for the route-level dependency."""

    def __init__(self, client: TestClient, user_id: str):
        self._client = client
        self._user_id = user_id

    def request(self, method: str, url: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(_signed_headers(method, url, self._user_id))
        return self._client.request(method, url, headers=headers, **kwargs)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


@pytest.fixture
def client():
    user_id = f"test-user-{uuid.uuid4()}"
    app.dependency_overrides[get_user_id] = lambda: user_id
    try:
        yield _SigningClient(TestClient(app), user_id), user_id
    finally:
        app.dependency_overrides.pop(get_user_id, None)


def _valid_payload(name: str = "My view") -> dict:
    return {"name": name, "filters": {"account_ids": [], "account_types": [], "currencies": []}}


# ---------------------------------------------------------------------------
# Finding 1: max_length on filter lists and the per-user saved-view cap
# ---------------------------------------------------------------------------


def test_filter_list_longer_than_max_length_is_rejected(client, fake_redis):
    signing_client, _ = client
    payload = _valid_payload()
    payload["filters"]["account_ids"] = [str(uuid.uuid4()) for _ in range(saved_views.MAX_FILTER_LIST_LENGTH + 1)]

    resp = signing_client.post("/api/saved-views/", json=payload)

    assert resp.status_code == 422, resp.text


def test_exceeding_saved_view_cap_returns_409(client, fake_redis):
    signing_client, user_id = client

    # Pre-seed the store at the cap directly, bypassing the API, so this
    # test doesn't depend on making MAX_SAVED_VIEWS_PER_USER real requests.
    existing = [
        {
            "id": str(uuid.uuid4()),
            "name": f"view-{i}",
            "filters": {"account_ids": [], "account_types": [], "currencies": []},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        for i in range(saved_views.MAX_SAVED_VIEWS_PER_USER)
    ]
    fake_redis.set(saved_views._redis_key(user_id), json.dumps(existing))

    resp = signing_client.post("/api/saved-views/", json=_valid_payload("one too many"))

    assert resp.status_code == 409, resp.text
    assert str(saved_views.MAX_SAVED_VIEWS_PER_USER) in resp.json()["detail"]

    # The cap must not have let the write through.
    stored = json.loads(fake_redis.store[saved_views._redis_key(user_id)])
    assert len(stored) == saved_views.MAX_SAVED_VIEWS_PER_USER


def test_create_under_cap_succeeds(client, fake_redis):
    signing_client, user_id = client

    resp = signing_client.post("/api/saved-views/", json=_valid_payload("under cap"))

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "under cap"
    stored = json.loads(fake_redis.store[saved_views._redis_key(user_id)])
    assert len(stored) == 1
    assert stored[0]["id"] == body["id"]


# ---------------------------------------------------------------------------
# Finding 3: corrupt blob is preserved at a side key and list returns []
# ---------------------------------------------------------------------------


def _corrupt_keys_for(fake_redis, user_id: str) -> list[str]:
    prefix = f"{saved_views._redis_key(user_id)}:corrupt:"
    return [k for k in fake_redis.store if k.startswith(prefix)]


def test_corrupt_blob_returns_empty_list_and_is_preserved(client, fake_redis):
    signing_client, user_id = client
    corrupt_raw = "{not valid json::"
    fake_redis.set(saved_views._redis_key(user_id), corrupt_raw)

    resp = signing_client.get("/api/saved-views/")

    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    corrupt_keys = _corrupt_keys_for(fake_redis, user_id)
    assert len(corrupt_keys) == 1
    assert fake_redis.store[corrupt_keys[0]] == corrupt_raw


def test_second_corruption_does_not_overwrite_first_backup(client, fake_redis):
    # Finding 2 regression: the backup key must be unique per corruption
    # event so a second corruption doesn't destroy the first preserved blob.
    signing_client, user_id = client
    key = saved_views._redis_key(user_id)

    first_corrupt_raw = "{first corrupt blob::"
    fake_redis.set(key, first_corrupt_raw)
    resp = signing_client.get("/api/saved-views/")
    assert resp.status_code == 200, resp.text

    second_corrupt_raw = "{second corrupt blob::"
    fake_redis.set(key, second_corrupt_raw)
    resp = signing_client.get("/api/saved-views/")
    assert resp.status_code == 200, resp.text

    corrupt_keys = _corrupt_keys_for(fake_redis, user_id)
    assert len(corrupt_keys) == 2
    preserved_values = {fake_redis.store[k] for k in corrupt_keys}
    assert preserved_values == {first_corrupt_raw, second_corrupt_raw}


# ---------------------------------------------------------------------------
# Finding 4: one malformed entry is skipped, valid entries are still returned
# ---------------------------------------------------------------------------


def test_malformed_entry_is_skipped_valid_entries_returned(client, fake_redis):
    signing_client, user_id = client
    valid_entry = {
        "id": str(uuid.uuid4()),
        "name": "Valid view",
        "filters": {"account_ids": [], "account_types": [], "currencies": []},
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    # Missing "id" and "created_at" — as an older revision might have written.
    malformed_entry = {
        "name": "Broken view",
        "filters": {"account_ids": [], "account_types": [], "currencies": []},
    }
    fake_redis.set(
        saved_views._redis_key(user_id),
        json.dumps([valid_entry, malformed_entry]),
    )

    resp = signing_client.get("/api/saved-views/")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == valid_entry["id"]
    assert body[0]["name"] == "Valid view"

    # A GET must not have rewritten the stored blob to drop the bad entry.
    stored = json.loads(fake_redis.store[saved_views._redis_key(user_id)])
    assert len(stored) == 2


# ---------------------------------------------------------------------------
# Atomicity: WATCH/MULTI/EXEC retry-on-conflict and retry-exhaustion (409)
#
# These rely on FakeRedis's real per-key version counter (see above) so a
# concurrent write between WATCH and EXEC is genuinely detected rather than
# assumed. Proof that this matters: comment out the `pipe.watch(key)` call
# in `app/routes/saved_views.py::_atomic_mutate` and re-run this file —
# `test_retry_exhaustion_returns_409` fails (409 never happens, because
# nothing ever conflicts) with the watch disabled, and passes once it is
# restored.
# ---------------------------------------------------------------------------


def test_concurrent_write_is_detected_and_retried(client, fake_redis):
    signing_client, user_id = client
    key = saved_views._redis_key(user_id)
    fake_redis.set(key, json.dumps([]))

    watch_calls = {"count": 0}
    intruder = {
        "id": "intruder",
        "name": "sneaked in",
        "filters": {"account_ids": [], "account_types": [], "currencies": []},
        "created_at": "2026-01-01T00:00:00+00:00",
    }

    def sneak_in_on_first_watch(watched_key: str) -> None:
        watch_calls["count"] += 1
        if watch_calls["count"] == 1 and watched_key == key:
            # Simulate a concurrent writer committing a change right after
            # our WATCH is taken but before our EXEC — this must bump the
            # key's version so the upcoming execute() raises WatchError.
            fake_redis.set(key, json.dumps([intruder]))

    fake_redis.on_watch = sneak_in_on_first_watch

    resp = signing_client.post("/api/saved-views/", json=_valid_payload("retry me"))

    assert resp.status_code == 201, resp.text
    # More than one attempt occurred: the first watch conflicted and
    # triggered a retry, the second succeeded uncontested.
    assert watch_calls["count"] >= 2

    stored = json.loads(fake_redis.store[key])
    # The retry must have re-read post-conflict state (the intruder's
    # write) rather than clobbering it — both entries are present.
    assert len(stored) == 2
    ids = {v["id"] for v in stored}
    assert "intruder" in ids


def test_retry_exhaustion_returns_409(client, fake_redis):
    signing_client, user_id = client
    key = saved_views._redis_key(user_id)
    fake_redis.set(key, json.dumps([]))

    watch_calls = {"count": 0}

    def always_conflict(watched_key: str) -> None:
        if watched_key == key:
            watch_calls["count"] += 1
            # Bump the version on every single watch so every attempt
            # conflicts — the loop must exhaust MAX_LOCK_RETRIES and 409,
            # never loop forever and never spuriously succeed.
            fake_redis.set(key, json.dumps([]))

    fake_redis.on_watch = always_conflict

    resp = signing_client.post("/api/saved-views/", json=_valid_payload("never succeeds"))

    assert resp.status_code == 409, resp.text
    assert watch_calls["count"] == saved_views.MAX_LOCK_RETRIES

    # The write must never have gone through.
    stored = json.loads(fake_redis.store[key])
    assert stored == []


# ---------------------------------------------------------------------------
# Finding 2 (smoke check): delete uses the same atomic path and 404s cleanly
# ---------------------------------------------------------------------------


def test_delete_missing_view_returns_404(client, fake_redis):
    signing_client, user_id = client
    fake_redis.set(saved_views._redis_key(user_id), json.dumps([]))

    resp = signing_client.delete(f"/api/saved-views/{uuid.uuid4()}")

    assert resp.status_code == 404, resp.text


def test_create_then_delete_round_trip(client, fake_redis):
    signing_client, user_id = client

    create_resp = signing_client.post("/api/saved-views/", json=_valid_payload("to delete"))
    view_id = create_resp.json()["id"]

    delete_resp = signing_client.delete(f"/api/saved-views/{view_id}")
    assert delete_resp.status_code == 204, delete_resp.text

    stored = json.loads(fake_redis.store[saved_views._redis_key(user_id)])
    assert stored == []
