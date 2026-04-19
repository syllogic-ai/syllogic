"""
API Key authentication for the MCP server.
Validates API keys and resolves them to user IDs.
"""
import hashlib
import os
import bcrypt
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

try:
    from fastmcp.server.auth import AuthProvider, AccessToken
except ImportError:  # pragma: no cover - fallback for environments without FastMCP
    class AuthProvider:  # type: ignore[override]
        pass

    @dataclass
    class AccessToken:  # type: ignore[override]
        token: str
        client_id: str
        scopes: list[str]
        expires_at: Optional[datetime]
        claims: dict[str, str]

from app.database import SessionLocal
from app.models import ApiKey


def hash_api_key(key: str) -> str:
    """
    Hash an API key using bcrypt with salt.

    For new keys, use this function to generate the hash to store.
    """
    return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(key: str, stored_hash: str) -> bool:
    """
    Verify an API key against its stored hash.

    Handles both bcrypt hashes (new) and SHA-256 hashes (legacy).
    """
    # Check if it's a bcrypt hash (starts with $2b$ or $2a$)
    if stored_hash.startswith("$2"):
        return bcrypt.checkpw(key.encode(), stored_hash.encode())

    # Legacy SHA-256 hash (64 hex characters)
    legacy_hash = hashlib.sha256(key.encode()).hexdigest()
    return legacy_hash == stored_hash


def validate_api_key(api_key: str) -> Optional[str]:
    """
    Validate an API key and return the associated user_id.

    Supports both bcrypt (new) and SHA-256 (legacy) hashed keys.
    Legacy keys are automatically migrated to bcrypt on first use.

    Args:
        api_key: The raw API key string (e.g., "pf_abc123...")

    Returns:
        The user_id if the key is valid, None otherwise.
    """
    if not api_key or not api_key.startswith("pf_"):
        return None

    db = SessionLocal()
    try:
        # For bcrypt, we need to check all keys since we can't look up by hash
        # First try legacy SHA-256 lookup for backwards compatibility
        legacy_hash = hashlib.sha256(api_key.encode()).hexdigest()
        record = db.query(ApiKey).filter(ApiKey.key_hash == legacy_hash).first()

        if record:
            # Found with legacy hash - migrate to bcrypt
            record.key_hash = hash_api_key(api_key)
            db.commit()
        else:
            # Try to find a bcrypt-hashed key, scoped by key prefix when possible.
            key_prefix = api_key[:11]  # "pf_" + 8 chars
            candidates = db.query(ApiKey).filter(ApiKey.key_prefix == key_prefix).all()
            if not candidates:
                candidates = db.query(ApiKey).all()
            for key_record in candidates:
                if verify_api_key(api_key, key_record.key_hash):
                    record = key_record
                    break

        if not record:
            return None

        # Check if expired
        if record.expires_at and record.expires_at < datetime.utcnow():
            return None

        # Update last_used_at timestamp
        record.last_used_at = datetime.utcnow()
        db.commit()

        return record.user_id
    finally:
        db.close()


class ApiKeyAuthProvider(AuthProvider):
    """
    FastMCP auth provider that validates API keys from Authorization headers.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        user_id = validate_api_key(token)
        if not user_id:
            return None
        # Use user_id as client_id; include it in claims for easy access.
        return AccessToken(
            token=token,
            client_id=user_id,
            scopes=["mcp"],
            expires_at=None,
            claims={"user_id": user_id},
        )


try:
    from fastmcp.server.auth.providers.jwt import JWTVerifier
except ImportError:  # pragma: no cover
    JWTVerifier = None  # type: ignore


AS_ISSUER = os.environ.get("MCP_OAUTH_ISSUER", "https://app.syllogic.ai")
AS_JWKS_URI = os.environ.get(
    "MCP_OAUTH_JWKS_URI", "https://app.syllogic.ai/.well-known/jwks.json"
)
MCP_AUDIENCE = os.environ.get("MCP_OAUTH_AUDIENCE", "https://mcp.syllogic.ai")


class CompositeAuthProvider(AuthProvider):
    """
    Accepts either a pf_ API key (existing DB-backed) or a JWT issued by
    the Syllogic Authorization Server (better-auth on app.syllogic.ai).

    Prefix-gating: tokens starting with 'pf_' go to ApiKeyAuthProvider;
    everything else is treated as a JWT. This keeps the two paths fully
    disjoint.
    """

    # RemoteAuthProvider reads this off the wrapped token verifier when
    # computing its own required_scopes; default to empty list.
    required_scopes: list[str] = []

    def __init__(self) -> None:
        if JWTVerifier is None:
            raise RuntimeError(
                "fastmcp.server.auth.providers.jwt.JWTVerifier is required "
                "for CompositeAuthProvider. Bump fastmcp."
            )
        self.api_key = ApiKeyAuthProvider()
        self.jwt = JWTVerifier(
            jwks_uri=AS_JWKS_URI,
            issuer=AS_ISSUER,
            audience=MCP_AUDIENCE,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        if token.startswith("pf_"):
            return await self.api_key.verify_token(token)
        access = await self.jwt.verify_token(token)
        if access is None:
            return None
        if "user_id" not in access.claims:
            access.claims["user_id"] = access.claims.get("sub", "")
        return access
