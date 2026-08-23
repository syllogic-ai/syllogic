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
get/set/pipeline(WATCH/MULTI/EXEC) surface that `_atomic_mutate` exercises.

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
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str):
        self.store[key] = value
        return True

    def pipeline(self, transaction: bool = True):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, client: FakeRedis):
        self._client = client
        self._queued: list[tuple[str, str]] = []
        self._in_multi = False

    def watch(self, key: str):
        # No real concurrency in these tests; watch is a no-op marker.
        return None

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
        for key, value in self._queued:
            self._client.set(key, value)
        results = [True] * len(self._queued)
        self._queued = []
        return results

    def reset(self):
        self._queued = []
        self._in_multi = False


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


def test_corrupt_blob_returns_empty_list_and_is_preserved(client, fake_redis):
    signing_client, user_id = client
    corrupt_raw = "{not valid json::"
    fake_redis.set(saved_views._redis_key(user_id), corrupt_raw)

    resp = signing_client.get("/api/saved-views/")

    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    corrupt_key = saved_views._corrupt_redis_key(user_id)
    assert fake_redis.store.get(corrupt_key) == corrupt_raw


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
