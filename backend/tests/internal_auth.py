"""
Helpers for generating signed internal auth headers in integration tests.
"""
import hashlib
import hmac
import os
import time


def build_internal_auth_headers(method: str, path_with_query: str, user_id: str) -> dict[str, str]:
    """
    Build signed headers accepted by backend internal auth middleware.
    """
    secret = os.getenv("INTERNAL_AUTH_SECRET", "").strip()
    if not secret:
        raise RuntimeError("INTERNAL_AUTH_SECRET is required for backend integration tests.")

    timestamp = str(int(time.time()))
    payload = "\n".join([method.upper(), path_with_query, user_id, timestamp])
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "X-Syllogic-User-Id": user_id,
        "X-Syllogic-Timestamp": timestamp,
        "X-Syllogic-Signature": signature,
    }
