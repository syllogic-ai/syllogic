"""Tests for CompositeAuthProvider (pf_ key + JWT)."""
import pytest
from unittest.mock import AsyncMock, patch

from app.mcp.auth import CompositeAuthProvider


@pytest.fixture
def provider():
    return CompositeAuthProvider()


class TestPfKeyRouting:
    @pytest.mark.asyncio
    async def test_pf_prefix_routes_to_api_key_provider(self, provider):
        fake_token = AsyncMock()
        fake_token.claims = {"user_id": "user_123"}
        with patch.object(
            provider.api_key, "verify_token", AsyncMock(return_value=fake_token)
        ) as m_api, patch.object(
            provider.jwt, "verify_token", AsyncMock()
        ) as m_jwt:
            result = await provider.verify_token("pf_abcdef123456")
        assert result is fake_token
        m_api.assert_awaited_once_with("pf_abcdef123456")
        m_jwt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_pf_returns_none(self, provider):
        with patch.object(
            provider.api_key, "verify_token", AsyncMock(return_value=None)
        ), patch.object(
            provider.jwt, "verify_token", AsyncMock()
        ) as m_jwt:
            result = await provider.verify_token("pf_bogus")
        assert result is None
        m_jwt.assert_not_awaited()  # never falls through for pf_ prefix


class TestJwtRouting:
    @pytest.mark.asyncio
    async def test_non_pf_routes_to_jwt(self, provider):
        fake_token = AsyncMock()
        fake_token.claims = {"sub": "user_456"}
        with patch.object(
            provider.api_key, "verify_token", AsyncMock()
        ) as m_api, patch.object(
            provider.jwt, "verify_token", AsyncMock(return_value=fake_token)
        ):
            result = await provider.verify_token("eyJhbGciOi...")
        assert result is fake_token
        m_api.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_jwt_user_id_normalized_from_sub(self, provider):
        fake_token = AsyncMock()
        fake_token.claims = {"sub": "user_789"}
        with patch.object(
            provider.jwt, "verify_token", AsyncMock(return_value=fake_token)
        ):
            result = await provider.verify_token("eyJhbGciOi...")
        assert result.claims["user_id"] == "user_789"
        assert result.claims["sub"] == "user_789"

    @pytest.mark.asyncio
    async def test_jwt_existing_user_id_preserved(self, provider):
        fake_token = AsyncMock()
        fake_token.claims = {"sub": "user_001", "user_id": "override_002"}
        with patch.object(
            provider.jwt, "verify_token", AsyncMock(return_value=fake_token)
        ):
            result = await provider.verify_token("eyJhbGciOi...")
        assert result.claims["user_id"] == "override_002"

    @pytest.mark.asyncio
    async def test_invalid_jwt_returns_none(self, provider):
        with patch.object(
            provider.jwt, "verify_token", AsyncMock(return_value=None)
        ):
            result = await provider.verify_token("eyJhbGciOi.bad")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_token_returns_none(self, provider):
        result = await provider.verify_token("")
        assert result is None
