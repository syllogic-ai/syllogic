import os
from .base import PriceProvider, PriceQuote, SymbolMatch
from .yahoo_provider import YahooPriceProvider

__all__ = ["PriceProvider", "PriceQuote", "SymbolMatch", "get_price_provider"]


def get_price_provider() -> PriceProvider:
    name = os.getenv("SYLLOGIC_PRICE_PROVIDER", "alpha_vantage").lower()
    if name == "yahoo":
        return YahooPriceProvider()
    if name == "alpha_vantage":
        from .alpha_vantage_provider import AlphaVantagePriceProvider
        return AlphaVantagePriceProvider(api_key=os.environ["SYLLOGIC_PRICE_PROVIDER_API_KEY"])
    raise ValueError(f"Unknown price provider: {name}")
