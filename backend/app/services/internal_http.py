"""Backend → frontend signed HTTP calls (mirror of frontend/lib/internal/sign.ts)."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

import httpx


def _secret() -> str:
    s = os.getenv("INTERNAL_AUTH_SECRET", "").strip()
    if not s:
        raise RuntimeError("INTERNAL_AUTH_SECRET not configured")
    return s


def _signature(method: str, path: str, user_id: str, ts: str) -> str:
    payload = "\n".join([method.upper(), path, user_id, ts])
    return hmac.new(_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def signed_post(
    url: str,
    *,
    path: str,
    user_id: str,
    json_body: dict[str, Any],
    timeout_seconds: float = 30.0,
) -> httpx.Response:
    ts = str(int(time.time()))
    headers = {
        "content-type": "application/json",
        "x-syllogic-user-id": user_id,
        "x-syllogic-timestamp": ts,
        "x-syllogic-signature": _signature("POST", path, user_id, ts),
    }
    return httpx.post(url, headers=headers, json=json_body, timeout=timeout_seconds)
