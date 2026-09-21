"""Postgres-backed request throttling.

Deliberately simple (fixed-window counters via an atomic upsert) rather than a
sliding-window or token-bucket scheme -- this is meant to stop obvious abuse
(credential stuffing, cost-burning LLM spam, unauthenticated key-guessing),
not to be a precise limiter.

Counters live in the "rate_limit_counters" table (UNLOGGED -- see
frontend/lib/db/migrations/0042_rate_limit_counters.manual.sql), one row per
key. window_start tracks which fixed window the count belongs to; the upsert
resets the count when the window has rolled over instead of relying on a
separate expiry.

Fails open: if the database is unreachable, requests are allowed through and
a warning is logged. Rate limiting is a defense-in-depth layer here, not a
hard dependency -- it must not become a new way to take the app down.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import time
from typing import Optional, Sequence

from sqlalchemy import text
from starlette.responses import JSONResponse

from app.database import engine

logger = logging.getLogger(__name__)

_UPSERT_SQL = text(
    """
    INSERT INTO rate_limit_counters (key, window_start, count)
    VALUES (:key, :bucket, 1)
    ON CONFLICT (key) DO UPDATE
    SET count = CASE WHEN rate_limit_counters.window_start = EXCLUDED.window_start
                      THEN rate_limit_counters.count + 1
                      ELSE 1 END,
        window_start = EXCLUDED.window_start
    RETURNING count
    """
)


def is_rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
    """Returns True if `key` has exceeded `max_requests` in the current
    `window_seconds`-wide fixed window."""
    try:
        # Store the window's start as absolute epoch seconds (not a raw
        # bucket index) -- callers use different window_seconds (60s for the
        # IP limiter, 3600s for the LLM limiter), and a raw bucket index
        # isn't comparable across those scales when pruning old rows.
        window_start = (int(time.time()) // window_seconds) * window_seconds
        with engine.begin() as conn:
            count = conn.execute(_UPSERT_SQL, {"key": key, "bucket": window_start}).scalar_one()
        return count > max_requests
    except Exception:
        logger.warning(
            "Rate limiter backend unreachable; allowing request (fail-open).",
            exc_info=True,
        )
        return False


def _parse_networks(
    raw: Optional[str],
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Parse TRUSTED_PROXIES: a comma-separated list of addresses or CIDRs."""
    networks = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            # A typo here must not silently widen trust, and must not take the
            # server down either -- drop the entry and say so.
            logger.warning("Ignoring unparseable TRUSTED_PROXIES entry: %r", part)
    return tuple(networks)


# Which peers are allowed to speak for someone else via X-Forwarded-For.
# Empty (the default) means nobody: the TCP peer is the client, full stop.
TRUSTED_PROXIES = _parse_networks(os.getenv("TRUSTED_PROXIES"))


def _in_networks(address: str, networks: Sequence) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(parsed in network for network in networks)


def client_address(scope, trusted_proxies: Sequence = ()) -> str:
    """The address to throttle on.

    `scope["client"]` is the TCP peer. Behind a reverse proxy that is always
    the proxy, so every remote caller shares one bucket: the limiter either
    throttles legitimate traffic or gets raised until it protects nothing.

    X-Forwarded-For fixes that but is written by the client, so it is
    consulted only when the peer is a configured trusted proxy, and only the
    rightmost hop that isn't itself trusted is believed -- everything further
    left was appended by someone with no reason to be trusted, including an
    attacker who prepends a forged chain to dodge their own bucket.
    """
    client = scope.get("client")
    peer = client[0] if client else "unknown"
    if not trusted_proxies or not _in_networks(peer, trusted_proxies):
        return peer

    hops: list[str] = []
    for name, value in scope.get("headers") or ():
        if name.lower() == b"x-forwarded-for":
            hops.extend(hop.strip() for hop in value.decode("latin-1").split(","))

    for hop in reversed(hops):
        if not hop or _in_networks(hop, trusted_proxies):
            continue
        try:
            ipaddress.ip_address(hop)
        except ValueError:
            # Garbage in the chain: stop trusting the rest of it.
            break
        return hop

    return peer


class IPRateLimitMiddleware:
    """Starlette ASGI middleware: throttles by client IP.

    Used on the MCP HTTP app, which (unlike the main backend) receives
    requests directly from whoever can reach it -- including unauthenticated
    bearer/API-key presentation attempts -- rather than only from the
    internal-auth-signed Next.js proxy.

    Set TRUSTED_PROXIES when the server sits behind a reverse proxy; see
    `client_address` for why it is off by default.
    """

    def __init__(
        self,
        app,
        max_requests: int = 60,
        window_seconds: int = 60,
        exempt_paths: frozenset[str] = frozenset({"/health"}),
        trusted_proxies: Optional[Sequence] = None,
    ) -> None:
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exempt_paths = exempt_paths
        self.trusted_proxies = (
            TRUSTED_PROXIES if trusted_proxies is None else tuple(trusted_proxies)
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        client_ip = client_address(scope, self.trusted_proxies)

        if is_rate_limited(f"mcp-ip:{client_ip}", self.max_requests, self.window_seconds):
            response = JSONResponse(
                {"detail": "Too many requests. Please try again later."},
                status_code=429,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
