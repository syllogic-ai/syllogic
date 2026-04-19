#!/usr/bin/env python3
"""
Headless end-to-end test of the Syllogic OAuth 2.1 + MCP flow.

Simulates exactly what Claude's custom connector does:
  1. Dynamic Client Registration (DCR)
  2. Sign up / sign in a test user
  3. /oauth2/authorize with PKCE + resource indicator
  4. /oauth2/consent (accept)
  5. /oauth2/token exchange
  6. POST /mcp with the JWT

Usage:
    python scripts/test_oauth_e2e.py

Env overrides:
    FRONTEND_BASE (default http://localhost:3000)
    MCP_BASE (default http://localhost:8001)
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.parse
import requests

FRONTEND = os.environ.get("FRONTEND_BASE", "http://localhost:3000")
MCP = os.environ.get("MCP_BASE", "http://localhost:8001")
EMAIL = "e2e-tester@syllogic.local"
PASSWORD = "e2e-tester-password-1234"
NAME = "E2E Tester"


def log(step, data=""):
    print(f"\n=== {step} ===")
    if data:
        print(data if isinstance(data, str) else json.dumps(data, indent=2)[:2000])


def pkce():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def decode_jwt_payload(token):
    parts = token.split(".")
    if len(parts) < 2:
        return None
    pad = "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(parts[1] + pad))


def main():
    s = requests.Session()

    # 1. Sign up test user (idempotent; ignore if exists)
    log("Sign up / sign in")
    r = s.post(
        f"{FRONTEND}/api/auth/sign-up/email",
        json={"email": EMAIL, "password": PASSWORD, "name": NAME},
    )
    if r.status_code not in (200, 201):
        # Probably already exists → sign in
        r = s.post(
            f"{FRONTEND}/api/auth/sign-in/email",
            json={"email": EMAIL, "password": PASSWORD},
        )
    r.raise_for_status()
    log("session cookies", dict(s.cookies))

    # 2. DCR (use a fresh session — unauthenticated DCR)
    log("Dynamic Client Registration")
    r = requests.post(
        f"{FRONTEND}/api/auth/oauth2/register",
        json={
            "client_name": "E2E Test Client",
            "redirect_uris": ["http://localhost:9999/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:access",
        },
    )
    r.raise_for_status()
    client = r.json()
    log("client", client)
    client_id = client["client_id"]

    # 3. Authorize (with PKCE + resource indicator)
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(16)
    resource = f"{MCP}/mcp"
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": "http://localhost:9999/callback",
        "scope": "mcp:access",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": resource,
    }
    log("GET /oauth2/authorize", urllib.parse.urlencode(auth_params))
    r = s.get(
        f"{FRONTEND}/api/auth/oauth2/authorize",
        params=auth_params,
        allow_redirects=False,
    )
    log("authorize status", f"{r.status_code} loc={r.headers.get('location')}")

    # Expect redirect to /oauth/consent?... or direct to callback if auto-approved
    loc = r.headers.get("location", "")
    if "/oauth/consent" in loc:
        # Parse oauth_query back out
        consent_url = urllib.parse.urlparse(loc)
        oauth_query = urllib.parse.parse_qs(consent_url.query)
        # Better-auth expects the entire query string as oauth_query
        raw_q = consent_url.query
        log("POST /oauth2/consent", raw_q[:300])
        r = s.post(
            f"{FRONTEND}/api/auth/oauth2/consent",
            json={
                "accept": True,
                "scope": "mcp:access",
                "oauth_query": raw_q,
            },
            headers={"Origin": FRONTEND},
            allow_redirects=False,
        )
        log("consent status", f"{r.status_code} body={r.text[:500]}")
        try:
            body = r.json()
        except Exception:
            body = {}
        # Expect {redirect: true, url: "http://localhost:9999/callback?code=..."}
        cb_url = body.get("url") or body.get("redirect_uri")
        if not cb_url:
            # Maybe direct 302
            cb_url = r.headers.get("location")
        if not cb_url:
            print("!! no redirect url in consent response")
            sys.exit(1)
    elif "code=" in loc:
        cb_url = loc
    else:
        print(f"!! unexpected authorize redirect: {loc}")
        sys.exit(1)

    log("callback URL", cb_url)
    parsed = urllib.parse.urlparse(cb_url)
    code = urllib.parse.parse_qs(parsed.query).get("code", [None])[0]
    if not code:
        print("!! no code in callback URL")
        sys.exit(1)

    # 4. Token exchange
    log("POST /oauth2/token")
    r = requests.post(
        f"{FRONTEND}/api/auth/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:9999/callback",
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": resource,
        },
    )
    log("token status", r.status_code)
    r.raise_for_status()
    tok = r.json()
    log("token response", {k: v for k, v in tok.items() if k != "access_token"})
    access_token = tok["access_token"]
    claims = decode_jwt_payload(access_token)
    log("JWT claims", claims)

    # 5. Call MCP
    log("POST /mcp")
    r = requests.post(
        f"{MCP}/mcp",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        },
    )
    log("mcp status", f"{r.status_code}")
    log("mcp body", r.text[:1500])
    if r.status_code != 200:
        sys.exit(1)
    print("\n✅ E2E flow succeeded")


if __name__ == "__main__":
    main()
