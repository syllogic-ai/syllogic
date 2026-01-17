"""
Base adapter interface for bank integrations.
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel


class AccountData(BaseModel):
    """Canonical account data model."""
    external_id: str
    name: str
    account_type: str  # checking, savings, credit
    institution: str
    currency: str
    balance_available: Optional[Decimal] = None
    metadata: dict = {}


class TransactionData(BaseModel):
    """Canonical transaction data model."""
    external_id: str
    account_external_id: str
    amount: Decimal
    currency: str
    description: str
    merchant: Optional[str] = None
    booked_at: datetime
    transaction_type: str  # debit, credit
    pending: bool = False
    metadata: dict = {}


class BankAdapter(ABC):
    """Abstract base class for bank adapters."""
    
    @abstractmethod
    def fetch_accounts(self) -> List[AccountData]:
        """Fetch all accounts from the bank."""
        pass
    
    @abstractmethod
    def fetch_transactions(
        self,
        account_external_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[TransactionData]:
        """Fetch transactions for a specific account."""
        pass
    
    @abstractmethod
    def normalize_transaction(self, raw: dict) -> TransactionData:
        """Convert provider-specific transaction format to canonical format."""
        pass

