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


class TestCounterpartyIban(unittest.TestCase):
    def setUp(self):
        self.adapter = EnableBankingAdapter.__new__(EnableBankingAdapter)

    def test_normalize_extracts_counterparty_iban_from_creditor_account_iban(self):
        raw = {
            "transaction_id": "tx-1",
            "account_id": "acc-1",
            "transaction_amount": {"amount": "12.50", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "booking_date": "2026-04-01",
            "creditor_account": {"iban": "NL91 ABNA 0417 1643 00"},
            "debtor_account": {"iban": "NL02 RABO 0123 4567 89"},
            "creditor": {"name": "Some Merchant"},
        }
        txn = self.adapter.normalize_transaction(raw)
        # Outflow (DBIT) → counterparty is the creditor IBAN, stripped of spaces and upper-cased
        self.assertEqual(txn.counterparty_iban, "NL91ABNA0417164300")

    def test_normalize_extracts_counterparty_iban_from_nested_debtor(self):
        raw = {
            "transaction_id": "tx-2",
            "account_id": "acc-1",
            "transaction_amount": {"amount": "5.00", "currency": "EUR"},
            "credit_debit_indicator": "CRDT",
            "booking_date": "2026-04-01",
            "creditor_account": None,
            "debtor_account": None,
            "debtor": {"name": "Friend", "iban": "BE68539007547034"},
        }
        txn = self.adapter.normalize_transaction(raw)
        # Inflow (CRDT) → counterparty is the debtor IBAN
        self.assertEqual(txn.counterparty_iban, "BE68539007547034")

    def test_normalize_handles_missing_iban_gracefully(self):
        raw = {
            "transaction_id": "tx-3",
            "account_id": "acc-1",
            "transaction_amount": {"amount": "5.00", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "booking_date": "2026-04-01",
        }
        txn = self.adapter.normalize_transaction(raw)
        self.assertIsNone(txn.counterparty_iban)

    def test_normalize_ignores_non_iban_scheme(self):
        """BBAN / SORT and other non-IBAN schemes must NOT be extracted."""
        raw = {
            "transaction_id": "tx-4",
            "account_id": "acc-1",
            "transaction_amount": {"amount": "5.00", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "booking_date": "2026-04-01",
            "creditor_account": {"scheme_name": "BBAN", "identification": "12345678"},
        }
        txn = self.adapter.normalize_transaction(raw)
        self.assertIsNone(txn.counterparty_iban)

    def test_normalize_scheme_form_missing_identification(self):
        """``scheme_name: IBAN`` without ``identification`` must return None, not raise."""
        raw = {
            "transaction_id": "tx-5",
            "account_id": "acc-1",
            "transaction_amount": {"amount": "5.00", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "booking_date": "2026-04-01",
            "creditor_account": {"scheme_name": "IBAN"},
        }
        txn = self.adapter.normalize_transaction(raw)
        self.assertIsNone(txn.counterparty_iban)

    def test_normalize_creditor_account_takes_precedence_over_nested_creditor(self):
        """When both ``creditor_account`` and ``creditor`` carry an IBAN, the account
        object wins — it is authoritative."""
        raw = {
            "transaction_id": "tx-6",
            "account_id": "acc-1",
            "transaction_amount": {"amount": "5.00", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "booking_date": "2026-04-01",
            "creditor_account": {"iban": "NL91ABNA0417164300"},
            "creditor": {"name": "Some Merchant", "iban": "DE89370400440532013000"},
        }
        txn = self.adapter.normalize_transaction(raw)
        self.assertEqual(txn.counterparty_iban, "NL91ABNA0417164300")


class TestFetchAccountsIban(unittest.TestCase):
    """fetch_accounts must populate AccountData.iban from the raw EB session response."""

    def setUp(self):
        # Bypass __init__ — we don't need the real HTTP client to test transformation
        self.adapter = EnableBankingAdapter.__new__(EnableBankingAdapter)
        self.adapter.session_id = "session-123"

    def test_fetch_accounts_extracts_iban_from_raw(self):
        """A session-data response with iban populated must surface it on AccountData."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "aspsp": {"name": "ABN AMRO"},
            "accounts": [
                {
                    "uid": "acc-1",
                    "iban": "NL91 ABNA 0417 1643 00",
                    "account_name": "Main Checking",
                    "cash_account_type": "CACC",
                    "currency": "EUR",
                },
            ],
        }
        self.adapter.client = MagicMock()
        self.adapter.client.get.return_value = mock_response

        accounts = self.adapter.fetch_accounts()

        self.assertEqual(len(accounts), 1)
        # IBAN is normalized at the adapter layer via _extract_iban (spaces
        # stripped, upper-cased) so downstream consumers always see the
        # canonical form.
        self.assertEqual(accounts[0].iban, "NL91ABNA0417164300")

    def test_fetch_accounts_iban_is_none_when_missing(self):
        """Accounts without an IBAN (e.g. some credit cards) must yield iban=None."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "aspsp": {"name": "ABN AMRO"},
            "accounts": [
                {
                    "uid": "acc-2",
                    "account_name": "Credit Card",
                    "cash_account_type": "CARD",
                    "currency": "EUR",
                },
            ],
        }
        self.adapter.client = MagicMock()
        self.adapter.client.get.return_value = mock_response

        accounts = self.adapter.fetch_accounts()

        self.assertEqual(len(accounts), 1)
        self.assertIsNone(accounts[0].iban)


class TestFetchAccountIban(unittest.TestCase):
    """fetch_account_iban must extract IBAN from the nested
    ``account_id.iban`` shape returned by GET /accounts/{uid}/details."""

    def setUp(self):
        self.adapter = EnableBankingAdapter.__new__(EnableBankingAdapter)
        self.adapter.session_id = "session-123"

    def test_extracts_iban_from_nested_account_id(self):
        """The /details endpoint nests IBAN under account_id, not at top level."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "account_id": {"iban": "NL91 ABNA 0417 1643 00"},
            "all_account_ids": [{"identification": "12345", "scheme_name": "BBAN"}],
            "name": "Main Checking",
            "uid": "abc-123",
        }
        self.adapter.client = MagicMock()
        self.adapter.client.get.return_value = mock_response

        iban = self.adapter.fetch_account_iban("abc-123")

        self.assertEqual(iban, "NL91ABNA0417164300")
        self.adapter.client.get.assert_called_once_with("/accounts/abc-123/details")

    def test_falls_back_to_all_account_ids_when_primary_missing(self):
        """If account_id.iban isn't present, all_account_ids[] may carry it."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "account_id": {"identification": "fallback", "scheme_name": "BBAN"},
            "all_account_ids": [
                {"identification": "fallback", "scheme_name": "BBAN"},
                {"iban": "DE89 3704 0044 0532 0130 00"},
            ],
        }
        self.adapter.client = MagicMock()
        self.adapter.client.get.return_value = mock_response

        iban = self.adapter.fetch_account_iban("uid-2")

        self.assertEqual(iban, "DE89370400440532013000")

    def test_returns_none_when_no_iban_anywhere(self):
        """Some accounts (rare credit cards) genuinely don't have an IBAN."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "account_id": {"identification": "1234", "scheme_name": "BBAN"},
            "all_account_ids": [],
        }
        self.adapter.client = MagicMock()
        self.adapter.client.get.return_value = mock_response

        iban = self.adapter.fetch_account_iban("uid-3")

        self.assertIsNone(iban)


if __name__ == "__main__":
    unittest.main()
