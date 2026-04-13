"""Tests for Enable Banking adapter (transaction normalization + account mapping)."""

import os
import sys
import unittest
from decimal import Decimal
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.integrations.enable_banking_adapter import EnableBankingAdapter


class TestNormalizeTransaction(unittest.TestCase):
    def setUp(self):
        # Adapter doesn't need real credentials for normalization tests
        self.adapter = EnableBankingAdapter.__new__(EnableBankingAdapter)

    def test_normalize_debit_transaction(self):
        raw = {
            "entry_reference": "txn-001",
            "transaction_amount": {"amount": "-50.00", "currency": "EUR"},
            "remittance_information_unstructured": "Albert Heijn payment",
            "creditor_name": "Albert Heijn",
            "booking_date": "2026-03-15",
            "status": "BOOK",
        }
        result = self.adapter.normalize_transaction(raw)

        self.assertEqual(result.external_id, "txn-001")
        self.assertEqual(result.amount, Decimal("-50.00"))
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.transaction_type, "debit")
        self.assertEqual(result.merchant, "Albert Heijn")
        self.assertEqual(result.description, "Albert Heijn payment")
        self.assertFalse(result.pending)

    def test_normalize_credit_transaction(self):
        raw = {
            "entry_reference": "txn-002",
            "transaction_amount": {"amount": "1200.00", "currency": "EUR"},
            "remittance_information_unstructured": "Salary payment",
            "debtor_name": "Employer BV",
            "booking_date": "2026-03-01",
            "status": "BOOK",
        }
        result = self.adapter.normalize_transaction(raw)

        self.assertEqual(result.amount, Decimal("1200.00"))
        self.assertEqual(result.transaction_type, "credit")
        self.assertEqual(result.merchant, "Employer BV")

    def test_normalize_pending_transaction(self):
        raw = {
            "transaction_id": "txn-pending-1",
            "transaction_amount": {"amount": "-10.00", "currency": "EUR"},
            "remittance_information_unstructured": "Card payment",
            "booking_date": "2026-03-20",
            "status": "PDNG",
        }
        result = self.adapter.normalize_transaction(raw)

        self.assertEqual(result.external_id, "txn-pending-1")
        self.assertTrue(result.pending)

    def test_normalize_falls_back_to_transaction_id(self):
        raw = {
            "transaction_id": "fallback-id",
            "transaction_amount": {"amount": "-5.00", "currency": "EUR"},
            "remittance_information_unstructured": "Test",
            "booking_date": "2026-03-20",
            "status": "BOOK",
        }
        result = self.adapter.normalize_transaction(raw)
        self.assertEqual(result.external_id, "fallback-id")


class TestMapAccountType(unittest.TestCase):
    def setUp(self):
        self.adapter = EnableBankingAdapter.__new__(EnableBankingAdapter)

    def test_maps_cacc_to_checking(self):
        self.assertEqual(self.adapter._map_account_type("CACC"), "checking")

    def test_maps_svgs_to_savings(self):
        self.assertEqual(self.adapter._map_account_type("SVGS"), "savings")

    def test_maps_unknown_to_checking(self):
        self.assertEqual(self.adapter._map_account_type("XYZZ"), "checking")
        self.assertEqual(self.adapter._map_account_type(None), "checking")


if __name__ == "__main__":
    unittest.main()
