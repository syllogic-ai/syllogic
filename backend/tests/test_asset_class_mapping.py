"""Tests for the MCP asset-class mapping helper."""
import pytest

from app.mcp.tools._asset_class import (
    ASSET_CLASS_KEYS,
    account_type_to_asset_class,
)


class TestAccountTypeToAssetClass:
    def test_checking_maps_to_cash(self):
        assert account_type_to_asset_class("checking") == "cash"

    def test_savings_maps_to_savings(self):
        assert account_type_to_asset_class("savings") == "savings"

    def test_credit_maps_to_other(self):
        assert account_type_to_asset_class("credit") == "other"

    def test_investment_and_brokerage_map_to_investment(self):
        assert account_type_to_asset_class("investment") == "investment"
        assert account_type_to_asset_class("brokerage") == "investment"

    def test_crypto_property_vehicle_self(self):
        assert account_type_to_asset_class("crypto") == "crypto"
        assert account_type_to_asset_class("property") == "property"
        assert account_type_to_asset_class("vehicle") == "vehicle"

    def test_case_insensitive(self):
        assert account_type_to_asset_class("SAVINGS") == "savings"
        assert account_type_to_asset_class("Checking") == "cash"

    def test_unknown_returns_other(self):
        assert account_type_to_asset_class("zzz") == "other"

    def test_none_returns_other(self):
        assert account_type_to_asset_class(None) == "other"


class TestAssetClassKeys:
    def test_includes_savings(self):
        assert "savings" in ASSET_CLASS_KEYS

    def test_includes_all_seven(self):
        assert ASSET_CLASS_KEYS == (
            "cash",
            "savings",
            "investment",
            "crypto",
            "property",
            "vehicle",
            "other",
        )
