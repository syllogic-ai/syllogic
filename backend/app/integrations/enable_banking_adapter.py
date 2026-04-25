"""
Enable Banking adapter implementing the BankAdapter interface.

Fetches accounts, transactions, and balances from the Enable Banking REST API.
"""

import hashlib
import logging
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from app.integrations.base import BankAdapter, AccountData, TransactionData
from app.integrations.enable_banking_auth import EnableBankingClient


def _extract_iban(account_obj: Optional[dict]) -> Optional[str]:
    """Extract a normalized IBAN string from an EB account object.

    EB returns counterparty accounts either flat as ``{"iban": "..."}`` or in
    scheme form as ``{"scheme_name": "IBAN", "identification": "..."}``.
    Non-IBAN schemes (BBAN, SORT, etc.) and partial objects return None.
    Returns the IBAN with spaces removed and upper-cased, or None.
    """
    if not isinstance(account_obj, dict):
        return None
    iban = account_obj.get("iban")
    if isinstance(iban, str) and iban:
        return iban.replace(" ", "").upper()
    if (account_obj.get("scheme_name") or "").upper() == "IBAN":
        ident = account_obj.get("identification")
        if isinstance(ident, str) and ident:
            return ident.replace(" ", "").upper()
    return None


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
                iban=_extract_iban(acc),
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
        max_pages = 200  # guard against infinite loops from broken continuation keys
        page = 0
        while page < max_pages:
            page += 1
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
        else:
            raise RuntimeError(
                f"[EB] Pagination guard hit for account {account_external_id} after {max_pages} pages; "
                f"aborting to avoid partial sync"
            )

        return all_transactions

    def normalize_transaction(self, raw: dict) -> TransactionData:
        """Map EB transaction to canonical format."""
        amount = Decimal(str(raw["transaction_amount"]["amount"]))
        # EB uses entry_reference as primary ID; fall back to transaction_id.
        # Some banks (e.g. ABN AMRO fee transactions) provide neither — generate a
        # deterministic synthetic ID so Pydantic validation never fails and repeated
        # syncs produce the same ID for the same transaction.
        external_id = raw.get("entry_reference") or raw.get("transaction_id") or None
        if not external_id:
            _ri = raw.get("remittance_information")
            _ri_str = "|".join(_ri) if isinstance(_ri, list) and _ri else (_ri or "")
            _parts = "|".join([
                raw.get("booking_date") or raw.get("value_date") or "",
                str(raw["transaction_amount"]["amount"]),
                raw["transaction_amount"].get("currency", ""),
                _ri_str,
            ])
            external_id = "synth-" + hashlib.sha256(_parts.encode()).hexdigest()[:16]

        # Resolve nested creditor/debtor names (EB may use objects or flat fields)
        creditor_name = (
            raw.get("creditor_name")
            or (raw.get("creditor") or {}).get("name")
        )
        debtor_name = (
            raw.get("debtor_name")
            or (raw.get("debtor") or {}).get("name")
        )

        # Resolve structured remittance_information array (list of strings)
        remittance_info = raw.get("remittance_information")
        remittance_info_text = (
            " ".join(remittance_info) if isinstance(remittance_info, list) and remittance_info
            else (remittance_info if isinstance(remittance_info, str) else None)
        )

        # Build a rich description by combining all available EB text fields.
        # Previously used `or` (first non-null wins); now we concatenate so all
        # structured remittance lines, additional info, and notes are preserved.
        desc_parts: list[str] = []

        riu = raw.get("remittance_information_unstructured")
        if riu:
            desc_parts.append(riu)

        for item in (raw.get("remittance_information_unstructured_array") or []):
            if item and item not in desc_parts:
                desc_parts.append(item)

        if remittance_info_text and remittance_info_text not in desc_parts:
            desc_parts.append(remittance_info_text)

        ai_info = raw.get("additional_information")
        if ai_info and ai_info not in desc_parts:
            desc_parts.append(ai_info)

        note = raw.get("note")
        if note and note not in desc_parts:
            desc_parts.append(note)

        description = (
            " | ".join(desc_parts)
            if desc_parts
            else (creditor_name or debtor_name or raw.get("reference_number") or "")
        )

        merchant = creditor_name or debtor_name

        # EB always returns positive transaction amounts; direction is given by
        # credit_debit_indicator ("CRDT" = money in, "DBIT" = money out).
        # Normalise to signed amounts so downstream categorisation works correctly.
        credit_debit = raw.get("credit_debit_indicator", "CRDT").upper()

        # Resolve counterparty IBAN: for debits the counterparty is the creditor;
        # for credits the counterparty is the debtor.
        creditor_iban = (
            _extract_iban(raw.get("creditor_account"))
            or _extract_iban(raw.get("creditor"))
        )
        debtor_iban = (
            _extract_iban(raw.get("debtor_account"))
            or _extract_iban(raw.get("debtor"))
        )
        counterparty_iban = creditor_iban if credit_debit == "DBIT" else debtor_iban

        if credit_debit == "DBIT" and amount > 0:
            amount = -amount

        return TransactionData(
            external_id=external_id,
            account_external_id=raw.get("account_id", ""),
            amount=amount,
            currency=raw["transaction_amount"]["currency"],
            description=description,
            merchant=merchant,
            creditor=creditor_name,
            debtor=debtor_name,
            counterparty_iban=counterparty_iban,
            booked_at=datetime.fromisoformat(_date_str) if (_date_str := (
                raw.get("booking_date")
                or raw.get("value_date")
                or raw.get("transaction_date")
            )) else datetime.now(timezone.utc),
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
