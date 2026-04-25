"""Mapping between Account.account_type values and MCP asset-class keys.

Mirrors the frontend taxonomy in `frontend/lib/assets/asset-category.ts`.
Keep these two in sync — both sides are intentionally explicit so neither
side has to ship the other's enum.
"""
from __future__ import annotations

from typing import Optional

ASSET_CLASS_KEYS: tuple[str, ...] = (
    "cash",
    "savings",
    "investment",
    "crypto",
    "property",
    "vehicle",
    "other",
)

_ACCOUNT_TYPE_TO_ASSET_CLASS: dict[str, str] = {
    "checking": "cash",
    "cash": "cash",
    "savings": "savings",
    "credit": "other",
    "credit_card": "other",
    "investment": "investment",
    "investment_brokerage": "investment",
    "investment_manual": "investment",
    "brokerage": "investment",
    "crypto": "crypto",
    "property": "property",
    "vehicle": "vehicle",
}


def account_type_to_asset_class(account_type: Optional[str]) -> str:
    """Return the asset-class key for a given account_type. Falls back to 'other'."""
    if not account_type:
        return "other"
    return _ACCOUNT_TYPE_TO_ASSET_CLASS.get(account_type.lower(), "other")
