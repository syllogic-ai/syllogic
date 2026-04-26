"""Pin the factory to yfinance-only behaviour."""
import os
from unittest.mock import patch

from app.integrations.price_provider import get_price_provider
from app.integrations.price_provider.yahoo_provider import YahooPriceProvider


def test_factory_returns_yahoo_provider_with_no_env_vars():
    with patch.dict(os.environ, {}, clear=False):
        for var in ("SYLLOGIC_PRICE_PROVIDER", "SYLLOGIC_PRICE_PROVIDER_API_KEY"):
            os.environ.pop(var, None)
        provider = get_price_provider()
    assert isinstance(provider, YahooPriceProvider)
    assert provider.name == "yahoo"


def test_factory_ignores_legacy_env_vars():
    """Even if old env vars linger from a stale deployment, they have no effect."""
    with patch.dict(
        os.environ,
        {
            "SYLLOGIC_PRICE_PROVIDER": "alpha_vantage",
            "SYLLOGIC_PRICE_PROVIDER_API_KEY": "irrelevant",
        },
    ):
        provider = get_price_provider()
    assert isinstance(provider, YahooPriceProvider)
