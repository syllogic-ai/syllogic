"""
Enable Banking adapter implementing the BankAdapter interface.

Fetches accounts, transactions, and balances from the Enable Banking REST API.
"""

from typing import List, Optional
from decimal import Decimal
from datetime import datetime

from app.integrations.base import BankAdapter, AccountData, TransactionData
from app.integrations.enable_banking_auth import EnableBankingClient


# Mapping from Enable Banking cash account types to our canonical types
_ACCOUNT_TYPE_MAP = {
    "CACC": "checking",   # Current Account
    "SVGS": "savings",    # Savings Account
    "TRAN": "checking",   # Transaction Account
    "CASH": "checking",   # Cash Payment
    "CARD": "credit",     # Card Account
    "LOAN": "credit",     # Loan Account
    "MGLD": "savings",    # Managed Account
    "MOMA": "savings",    # Money Market Account
}


class EnableBankingAdapter(BankAdapter):
    """Adapter for Enable Banking REST API."""

    def __init__(self, session_id: str, client: Optional[EnableBankingClient] = None):
        """
        Args:
            session_id: Enable Banking session ID (obtained from POST /sessions).
            client: Optional pre-configured EnableBankingClient.
        """
        self.session_id = session_id
        self.client = client or EnableBankingClient()

    def _map_account_type(self, cash_account_type: Optional[str]) -> str:
        """Map EB cash account type to our canonical type."""
        if not cash_account_type:
            return "checking"
        return _ACCOUNT_TYPE_MAP.get(cash_account_type.upper(), "checking")

    def fetch_accounts(self) -> List[AccountData]:
        """Fetch accounts from the EB session."""
        resp = self.client.get(f"/sessions/{self.session_id}")
        session_data = resp.json()

        aspsp_name = session_data.get("aspsp", {}).get("name", "")
        accounts = []
        for acc in session_data.get("accounts", []):
            accounts.append(AccountData(
                external_id=acc["uid"],
                name=acc.get("account_name") or acc.get("iban") or "Unknown Account",
                account_type=self._map_account_type(acc.get("cash_account_type")),
                institution=aspsp_name,
                currency=acc.get("currency", "EUR"),
                balance_available=None,  # Fetched separately via fetch_balances
            ))
        return accounts

    def fetch_transactions(
        self,
        account_external_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[TransactionData]:
        """Fetch transactions with pagination via continuation_key."""
        all_transactions: List[TransactionData] = []
        params: dict = {}
        if start_date:
            params["date_from"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["date_to"] = end_date.strftime("%Y-%m-%d")

        continuation_key = None
        while True:
            if continuation_key:
                params["continuation_key"] = continuation_key

            resp = self.client.get(
                f"/accounts/{account_external_id}/transactions",
                params=params,
            )
            data = resp.json()

            for txn in data.get("transactions", []):
                all_transactions.append(self.normalize_transaction(txn))

            continuation_key = data.get("continuation_key")
            if not continuation_key:
                break

        return all_transactions

    def normalize_transaction(self, raw: dict) -> TransactionData:
        """Map EB transaction to canonical format."""
        import logging as _logging
        _log = _logging.getLogger(__name__)

        amount = Decimal(str(raw["transaction_amount"]["amount"]))
        # EB uses entry_reference as primary ID; fall back to transaction_id
        external_id = raw.get("entry_reference") or raw.get("transaction_id", "")

        # Log raw text fields to debug missing descriptions (TEMPORARY - remove after diagnosis)
        _log.info(
            "[EB_DEBUG] txn=%s amount=%s fields: riu=%r riua=%r ai=%r cn=%r dn=%r keys=%s",
            external_id,
            amount,
            raw.get("remittance_information_unstructured"),
            raw.get("remittance_information_unstructured_array"),
            raw.get("additional_information"),
            raw.get("creditor_name"),
            raw.get("debtor_name"),
            sorted(raw.keys()),
        )

        # Build description from multiple possible EB fields
        description = (
            raw.get("remittance_information_unstructured")
            or raw.get("remittance_information_unstructured_array", [""])[0]
            or raw.get("additional_information")
            or raw.get("creditor_name")
            or raw.get("debtor_name")
            or ""
        )

        merchant = raw.get("creditor_name") or raw.get("debtor_name")

        return TransactionData(
            external_id=external_id,
            account_external_id=raw.get("account_id", ""),
            amount=amount,
            currency=raw["transaction_amount"]["currency"],
            description=description,
            merchant=merchant,
            booked_at=datetime.fromisoformat(raw["booking_date"]),
            transaction_type="debit" if amount < 0 else "credit",
            pending=raw.get("status") == "PDNG",
            metadata={"raw": raw},
        )

    def fetch_balances(self, account_uid: str) -> dict:
        """
        Fetch account balances.

        Returns:
            Raw balance response dict with "balances" list.
        """
        resp = self.client.get(f"/accounts/{account_uid}/balances")
        return resp.json()
