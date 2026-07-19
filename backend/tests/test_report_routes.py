"""Tests for /api/reports routes.

Run with:
    cd backend && .venv/bin/pytest tests/test_report_routes.py -v
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-report-routes"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)
    os.environ.setdefault("INTERNAL_AUTH_SECRET", "test-internal-secret")


_set_test_env()

INTERNAL_AUTH_SECRET = os.environ["INTERNAL_AUTH_SECRET"]

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.db_helpers import get_user_id  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


def _seed_user(db) -> User:
    user = User(id=f"test-user-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com", name="Test User")
    db.add(user)
    db.commit()
    return user


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
    app.main's internal_auth_middleware) in addition to overriding
    get_user_id for the route-level dependency."""

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

    def patch(self, url, **kw):
        return self.request("PATCH", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


def _client_for_user(user_id: str) -> _SigningClient:
    app.dependency_overrides[get_user_id] = lambda: user_id
    return _SigningClient(TestClient(app), user_id)


def test_create_list_update_delete_report():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        client = _client_for_user(user.id)

        create_resp = client.post(
            "/api/reports",
            json={
                "name": "Weekly summary",
                "frequency": "WEEKLY",
                "send_day_of_week": 0,
                "recipient_emails": ["me@example.com"],
            },
        )
        assert create_resp.status_code == 200, create_resp.text
        report_id = create_resp.json()["id"]
        assert create_resp.json()["next_run_at"] is not None

        list_resp = client.get("/api/reports")
        assert list_resp.status_code == 200
        assert any(r["id"] == report_id for r in list_resp.json())

        patch_resp = client.patch(f"/api/reports/{report_id}", json={"is_active": False})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["is_active"] is False

        delete_resp = client.delete(f"/api/reports/{report_id}")
        assert delete_resp.status_code == 204

        get_resp = client.get(f"/api/reports/{report_id}")
        assert get_resp.status_code == 404
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()
        app.dependency_overrides.pop(get_user_id, None)


def test_create_report_rejects_invalid_frequency():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        client = _client_for_user(user.id)

        resp = client.post(
            "/api/reports",
            json={
                "name": "Yearly summary",
                "frequency": "YEARLY",
                "recipient_emails": ["me@example.com"],
            },
        )
        assert resp.status_code == 422, resp.text
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()
        app.dependency_overrides.pop(get_user_id, None)


def test_create_report_weekly_requires_send_day_of_week():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        client = _client_for_user(user.id)

        resp = client.post(
            "/api/reports",
            json={
                "name": "Weekly summary",
                "frequency": "WEEKLY",
                "recipient_emails": ["me@example.com"],
            },
        )
        assert resp.status_code == 422, resp.text
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()
        app.dependency_overrides.pop(get_user_id, None)
