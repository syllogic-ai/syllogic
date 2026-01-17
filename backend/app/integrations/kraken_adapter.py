"""
Kraken cryptocurrency exchange adapter.
Provides access to Kraken account balances, deposits, withdrawals, and trades.

Requirements:
    - Kraken account with API access
    - API Key and Private Key from Kraken settings

Documentation: https://docs.kraken.com/rest/

Rate Limiting:
    Kraken uses a "leaky bucket" rate limiting system:
    - Starter: Max 15 counter, -0.33/sec decay
    - Intermediate: Max 20 counter, -0.5/sec decay
    - Pro: Max 20 counter, -1/sec decay

    Add delays between API calls to avoid hitting rate limits.
    Recommended delays: Starter=3s, Intermediate=2s, Pro=1s
"""
import base64
import hashlib
import hmac
import time
import urllib.parse
import httpx
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from app.integrations.base import BankAdapter, AccountData, TransactionData

logger = logging.getLogger(__name__)


class KrakenAdapter(BankAdapter):
    """Adapter for Kraken cryptocurrency exchange integration."""

    # API Base URL
    BASE_URL = "https://api.kraken.com"
    API_VERSION = "0"

    def __init__(self, api_key: str, private_key: str):
        """
        Initialize Kraken adapter.

        Args:
            api_key: Kraken API key
            private_key: Kraken private key (base64 encoded)
        """
        self.api_key = api_key
        self.private_key = private_key

        # Initialize HTTP client
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            timeout=30.0,
            headers={
                "User-Agent": "Personal-Finance-App/1.0"
            }
        )

    def _get_kraken_signature(self, urlpath: str, data: Dict[str, Any], nonce: str) -> str:
        """
        Generate Kraken API signature for authenticated requests.

        Args:
            urlpath: API endpoint path
            data: Request data
            nonce: Nonce value

        Returns:
            Base64 encoded signature
        """
        postdata = urllib.parse.urlencode(data)
        encoded = (str(nonce) + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()

        signature = hmac.new(
            base64.b64decode(self.private_key),
            message,
            hashlib.sha512
        )
        return base64.b64encode(signature.digest()).decode()

    def _make_request(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        authenticated: bool = False
    ) -> Dict[str, Any]:
        """
        Make request to Kraken API.

        Args:
            endpoint: API endpoint (e.g., 'Balance', 'Ledgers')
            data: Request parameters
            authenticated: Whether request requires authentication

        Returns:
            Response data

        Raises:
            Exception: If request fails
        """
        if data is None:
            data = {}

        urlpath = f"/{self.API_VERSION}/private/{endpoint}" if authenticated else f"/{self.API_VERSION}/public/{endpoint}"

        headers = {}

        if authenticated:
            nonce = str(int(time.time() * 1000))
            data["nonce"] = nonce

            headers["API-Key"] = self.api_key
            headers["API-Sign"] = self._get_kraken_signature(urlpath, data, nonce)

        try:
            if authenticated or data:
                response = self.client.post(urlpath, data=data, headers=headers)
            else:
                response = self.client.get(urlpath, params=data)

            response.raise_for_status()
            result = response.json()

            # Kraken returns errors in 'error' field
            if result.get("error") and len(result["error"]) > 0:
                raise Exception(f"Kraken API error: {', '.join(result['error'])}")

            return result.get("result", {})

        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling Kraken API: {e}")
            raise Exception(f"Failed to call Kraken API: {e}")

    def get_account_balance(self) -> Dict[str, Decimal]:
        """
        Get account balances for all assets.

        Returns:
            Dictionary mapping asset name to balance
        """
        result = self._make_request("Balance", authenticated=True)

        balances = {}
        for asset, amount in result.items():
            try:
                balances[asset] = Decimal(amount)
            except (ValueError, TypeError):
                logger.warning(f"Could not parse balance for {asset}: {amount}")

        return balances

    def fetch_accounts(self) -> List[AccountData]:
        """
        Fetch all Kraken accounts (one per asset with non-zero balance).

        Returns:
            List of AccountData objects (one per cryptocurrency)
        """
        balances = self.get_account_balance()

        accounts = []
        for asset, balance in balances.items():
            # Skip assets with zero balance
            if balance <= 0:
                continue

            # Normalize asset name (Kraken uses X prefix for some assets)
            display_asset = self._normalize_asset_name(asset)

            accounts.append(AccountData(
                external_id=f"kraken_{asset}",
                name=f"Kraken {display_asset}",
                account_type="investment",  # Crypto is treated as investment
                institution="Kraken",
                currency=display_asset,
                balance_available=balance,  # All crypto is immediately available
                metadata={
                    "asset": asset,
                    "platform": "kraken",
                    "account_type": "spot"
                }
            ))

        return accounts

    def _normalize_asset_name(self, asset: str) -> str:
        """
        Normalize Kraken asset names (remove X/Z prefixes).

        Args:
            asset: Kraken asset name (e.g., XXBT, ZEUR)

        Returns:
            Normalized name (e.g., BTC, EUR)
        """
        # Kraken uses X prefix for crypto, Z for fiat
        # XXBT -> BTC, XETH -> ETH, ZEUR -> EUR, ZUSD -> USD
        asset_map = {
            "XXBT": "BTC",
            "XBT": "BTC",
            "XETH": "ETH",
            "XXDG": "DOGE",
            "XLTC": "LTC",
            "XXMR": "XMR",
            "XXRP": "XRP",
            "ZEUR": "EUR",
            "ZUSD": "USD",
            "ZGBP": "GBP",
            "ZCAD": "CAD",
            "ZJPY": "JPY",
        }

        return asset_map.get(asset, asset)

    def get_ledgers(
        self,
        asset: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        ledger_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get ledger entries (deposits, withdrawals, trades, etc.).

        Args:
            asset: Filter by specific asset
            start_time: Start date for ledger entries
            end_time: End date for ledger entries
            ledger_type: Type of ledger entry (deposit, withdrawal, trade, etc.)

        Returns:
            List of ledger entries
        """
        params = {}

        if asset:
            params["asset"] = asset

        if start_time:
            params["start"] = int(start_time.timestamp())

        if end_time:
            params["end"] = int(end_time.timestamp())

        if ledger_type:
            params["type"] = ledger_type

        result = self._make_request("Ledgers", data=params, authenticated=True)

        ledgers = []
        ledger_info = result.get("ledger", {})

        for ledger_id, ledger_data in ledger_info.items():
            ledger_data["id"] = ledger_id
            ledgers.append(ledger_data)

        return ledgers

    def fetch_transactions(
        self,
        account_external_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[TransactionData]:
        """
        Fetch transactions (ledger entries) for a specific asset.

        Args:
            account_external_id: Account ID (format: kraken_{asset})
            start_date: Start date for transactions
            end_date: End date for transactions

        Returns:
            List of TransactionData objects
        """
        # Extract asset from account ID
        asset = account_external_id.replace("kraken_", "")

        # Default to last 90 days if no dates provided
        if not start_date:
            start_date = datetime.now() - timedelta(days=90)
        if not end_date:
            end_date = datetime.now()

        # Get ledger entries
        ledgers = self.get_ledgers(
            asset=asset,
            start_time=start_date,
            end_time=end_date
        )

        transactions = []
        for ledger in ledgers:
            try:
                txn = self.normalize_transaction(ledger, account_external_id)
                transactions.append(txn)
            except Exception as e:
                logger.error(f"Error normalizing ledger entry: {e}")
                continue

        return transactions

    def normalize_transaction(
        self,
        raw: Dict[str, Any],
        account_external_id: Optional[str] = None
    ) -> TransactionData:
        """
        Convert Kraken ledger entry to TransactionData format.

        Args:
            raw: Raw ledger entry from Kraken API
            account_external_id: Account ID

        Returns:
            TransactionData object
        """
        # Extract data
        ledger_id = raw.get("id", "")
        refid = raw.get("refid", "")
        ledger_time = raw.get("time", time.time())
        ledger_type = raw.get("type", "")
        asset = raw.get("asset", "")
        amount = Decimal(str(raw.get("amount", "0")))
        fee = Decimal(str(raw.get("fee", "0")))
        balance = Decimal(str(raw.get("balance", "0")))

        # Determine transaction type
        transaction_type = "credit" if amount >= 0 else "debit"

        # Create description based on ledger type
        type_descriptions = {
            "deposit": "Deposit",
            "withdrawal": "Withdrawal",
            "trade": "Trade",
            "staking": "Staking Reward",
            "transfer": "Transfer",
            "margin": "Margin Trade",
            "rollover": "Rollover",
            "spend": "Spend",
            "receive": "Receive",
            "settled": "Settlement",
            "adjustment": "Adjustment",
        }

        description = type_descriptions.get(ledger_type, ledger_type.title())

        # Add asset to description
        normalized_asset = self._normalize_asset_name(asset)
        description = f"{description} - {normalized_asset}"

        # Parse timestamp
        try:
            booked_at = datetime.fromtimestamp(float(ledger_time))
        except (ValueError, TypeError):
            booked_at = datetime.now()

        # Use account_external_id or construct from asset
        if not account_external_id:
            account_external_id = f"kraken_{asset}"

        return TransactionData(
            external_id=ledger_id or refid,
            account_external_id=account_external_id,
            amount=amount,
            currency=normalized_asset,
            description=description,
            merchant="Kraken",
            booked_at=booked_at,
            transaction_type=transaction_type,
            pending=False,  # Kraken ledger entries are all settled
            metadata={
                "ledger_type": ledger_type,
                "refid": refid,
                "fee": str(fee),
                "balance": str(balance),
                "asset": asset,
            }
        )

    def get_deposit_methods(self, asset: str) -> List[Dict[str, Any]]:
        """
        Get available deposit methods for an asset.

        Args:
            asset: Asset name (e.g., BTC, ETH)

        Returns:
            List of deposit methods
        """
        result = self._make_request(
            "DepositMethods",
            data={"asset": asset},
            authenticated=True
        )
        return result

    def get_deposit_addresses(self, asset: str, method: str) -> List[Dict[str, Any]]:
        """
        Get deposit addresses for an asset.

        Args:
            asset: Asset name
            method: Deposit method

        Returns:
            List of deposit addresses
        """
        result = self._make_request(
            "DepositAddresses",
            data={"asset": asset, "method": method},
            authenticated=True
        )
        return result

    def get_trades_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get trade history.

        Args:
            start_time: Start date for trades
            end_time: End date for trades

        Returns:
            Dictionary of trades
        """
        params = {}

        if start_time:
            params["start"] = int(start_time.timestamp())

        if end_time:
            params["end"] = int(end_time.timestamp())

        result = self._make_request("TradesHistory", data=params, authenticated=True)
        return result

    def __del__(self):
        """Cleanup HTTP client on deletion."""
        if hasattr(self, 'client'):
            self.client.close()
