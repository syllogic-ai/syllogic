from .base import PriceProvider, PriceQuote, SymbolMatch
from .yahoo_provider import YahooPriceProvider

__all__ = ["PriceProvider", "PriceQuote", "SymbolMatch", "get_price_provider"]


def get_price_provider() -> PriceProvider:
    """Return the active price provider. yfinance-backed, no configuration."""
    return YahooPriceProvider()
