"""
Enable Banking API authentication and HTTP client.

Uses JWT (RS256) signed with the application's RSA private key.
See: https://enablebanking.com/docs/api/reference/
"""

import os
import time
from typing import Optional

import jwt
import requests
from cryptography.hazmat.primitives import serialization


def create_eb_jwt(application_id: str, private_key_pem: str, ttl: int = 3600) -> str:
    """
    Create a JWT for Enable Banking API authentication.

    Args:
        application_id: Enable Banking application ID (used as kid header).
        private_key_pem: RSA private key in PEM format.
        ttl: Token time-to-live in seconds (max 86400).

    Returns:
        Signed JWT string.
    """
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"), password=None
    )
    now = int(time.time())
    payload = {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": now,
        "exp": now + ttl,
    }
    headers = {
        "typ": "JWT",
        "alg": "RS256",
        "kid": application_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256", headers=headers)


class EnableBankingClient:
    """HTTP client for Enable Banking REST API."""

    def __init__(
        self,
        app_id: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        self.app_id = app_id or os.getenv("ENABLE_BANKING_APP_ID", "")
        self.redirect_uri = redirect_uri or os.getenv("ENABLE_BANKING_REDIRECT_URI", "")
        # Enable Banking uses the same API URL for sandbox and production;
        # the application credentials determine the environment.
        self.base_url = "https://api.enablebanking.com"

        # Load private key from env var or file path
        self._private_key_pem = private_key_pem
        if not self._private_key_pem:
            self._private_key_pem = os.getenv("ENABLE_BANKING_PRIVATE_KEY", "")
        if not self._private_key_pem:
            key_path = os.getenv("ENABLE_BANKING_PRIVATE_KEY_PATH", "")
            if key_path and os.path.exists(key_path):
                with open(key_path, "r") as f:
                    self._private_key_pem = f.read()

    def get_headers(self) -> dict:
        """Get authorization headers with a fresh JWT."""
        token = create_eb_jwt(self.app_id, self._private_key_pem)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get(self, path: str, params: Optional[dict] = None) -> requests.Response:
        """Make an authenticated GET request."""
        resp = requests.get(
            f"{self.base_url}{path}",
            headers=self.get_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    def post(self, path: str, json_data: Optional[dict] = None) -> requests.Response:
        """Make an authenticated POST request."""
        resp = requests.post(
            f"{self.base_url}{path}",
            headers=self.get_headers(),
            json=json_data,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    def delete(self, path: str) -> requests.Response:
        """Make an authenticated DELETE request."""
        resp = requests.delete(
            f"{self.base_url}{path}",
            headers=self.get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp
