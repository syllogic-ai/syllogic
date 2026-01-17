"""
Exchange rate service for fetching and managing currency conversion rates.
Uses Yahoo Finance API (via yfinance library) for batch fetching of historical rates.
Yahoo Finance is free and supports historical data from 1970 onwards.
"""
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging
import time

from app.models import ExchangeRate, Transaction
from app.database import SessionLocal

logger = logging.getLogger(__name__)

# Try to import yfinance
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError as e:
    yf = None
    YFINANCE_AVAILABLE = False
    logger.warning(f"yfinance package not available: {e}")


class ExchangeRateService:
    """Service for managing exchange rates using Yahoo Finance API."""

    # Default currencies to fetch if no transactions exist
    DEFAULT_CURRENCIES = ["EUR", "USD", "GBP", "JPY", "INR"]

    # Functional currencies supported (target currencies for conversion)
    FUNCTIONAL_CURRENCIES = ["EUR", "USD"]

    # Batch size for API calls (days per batch to avoid rate limits)
    BATCH_SIZE_DAYS = 365  # Yahoo Finance can handle larger batches

    def __init__(self, db: Session):
        self.db = db
        if not YFINANCE_AVAILABLE:
            raise ImportError(
                "yfinance package is not available. "
                "Please install it with: pip install yfinance"
            )
    
    @staticmethod
    def _get_yahoo_ticker(base_currency: str, target_currency: str) -> str:
        """
        Convert currency pair to Yahoo Finance ticker symbol.
        Format: {BASE}{TARGET}=X (e.g., EURUSD=X, GBPUSD=X)
        """
        return f"{base_currency}{target_currency}=X"

    def get_distinct_transaction_currencies(self) -> List[str]:
        """
        Get all distinct currencies from transactions.
        If no transactions, return default currencies.
        """
        try:
            # Query distinct currencies from transactions
            currencies = self.db.query(Transaction.currency).distinct().all()
            currency_list = [c[0] for c in currencies if c[0]]

            # If no currencies found, use defaults
            if not currency_list:
                logger.info("No currencies found in transactions, using defaults")
                return self.DEFAULT_CURRENCIES

            # Always include EUR and USD
            for curr in ["EUR", "USD"]:
                if curr not in currency_list:
                    currency_list.append(curr)

            logger.info(f"Found {len(currency_list)} distinct currencies: {currency_list}")
            return currency_list

        except Exception as e:
            logger.error(f"Error getting distinct currencies: {e}")
            return self.DEFAULT_CURRENCIES

    def fetch_exchange_rates_batch(
        self,
        base_currency: str,
        target_currencies: List[str],
        start_date: date,
        end_date: date
    ) -> Dict[date, Dict[str, Decimal]]:
        """
        Fetch exchange rates for a date range using Yahoo Finance API.
        
        Args:
            base_currency: Base currency (transaction currency) - what we're converting FROM
            target_currencies: List of target currencies (EUR, USD) - what we're converting TO
            start_date: Start date of the range
            end_date: End date of the range

        Returns:
            Dictionary mapping date -> {target_currency: rate}
            Where rate = how many target_currency = 1 base_currency
        """
        rates_by_date = {}
        
        # Convert dates to datetime for yfinance
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.min.time())
        
        # Fetch rates for each target currency
        for target_currency in target_currencies:
            try:
                # Handle self-conversion (e.g., EUR -> EUR)
                if base_currency == target_currency:
                    # Fill in 1.0 rates for all dates
                    current_date = start_date
                    while current_date <= end_date:
                        if current_date not in rates_by_date:
                            rates_by_date[current_date] = {}
                        rates_by_date[current_date][target_currency] = Decimal("1.0")
                        current_date += timedelta(days=1)
                    continue
                
                # Get Yahoo Finance ticker symbol
                ticker_symbol = self._get_yahoo_ticker(base_currency, target_currency)
                
                logger.debug(f"Fetching {ticker_symbol} from {start_date} to {end_date}")
                
                # Fetch historical data from Yahoo Finance
                ticker = yf.Ticker(ticker_symbol)
                hist = ticker.history(start=start_datetime, end=end_datetime)
                
                if hist.empty:
                    logger.warning(f"No data returned for {ticker_symbol}")
                    continue
                
                # Process historical data
                # Yahoo Finance returns: 1 base_currency = X target_currency (using Close price)
                for date_index, row in hist.iterrows():
                    # date_index is a Timestamp, convert to date
                    rate_date = date_index.date()
                    
                    # Use Close price as the exchange rate
                    rate_value = Decimal(str(row['Close']))
                    
                    if rate_date not in rates_by_date:
                        rates_by_date[rate_date] = {}
                    
                    rates_by_date[rate_date][target_currency] = rate_value
                
                logger.info(f"Fetched {len(hist)} rates for {base_currency} -> {target_currency}")
                
                # Small delay to avoid rate limiting
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error fetching rates for {base_currency} -> {target_currency}: {e}")
                # Continue with other currencies
                continue
        
        logger.info(f"Fetched rates for {len(rates_by_date)} dates from {start_date} to {end_date}")
        return rates_by_date
    
    def fetch_current_exchange_rates(
        self,
        base_currency: str,
        target_currencies: List[str]
    ) -> Dict[str, Decimal]:
        """
        Fetch current exchange rates using Yahoo Finance API.
        
        Args:
            base_currency: Base currency (transaction currency)
            target_currencies: List of target currencies (EUR, USD)

        Returns:
            Dictionary mapping target_currency -> rate
        """
        result_dict = {}
        
        # Fetch rates for each target currency
        for target_currency in target_currencies:
            try:
                # Handle self-conversion
                if base_currency == target_currency:
                    result_dict[target_currency] = Decimal("1.0")
                    continue
                
                # Get Yahoo Finance ticker symbol
                ticker_symbol = self._get_yahoo_ticker(base_currency, target_currency)
                
                # Fetch current rate (last 1 day of data)
                ticker = yf.Ticker(ticker_symbol)
                hist = ticker.history(period="1d")
                
                if hist.empty:
                    logger.warning(f"No current data for {ticker_symbol}")
                    continue
                
                # Use the most recent Close price
                latest_rate = hist['Close'].iloc[-1]
                result_dict[target_currency] = Decimal(str(latest_rate))
                
            except Exception as e:
                logger.error(f"Error fetching current rate for {base_currency} -> {target_currency}: {e}")
                # Continue with other currencies
                continue
        
        return result_dict

    def store_exchange_rates(
        self,
        target_currency: str,
        rates: Dict[str, Decimal],
        for_date: date
    ) -> int:
        """
        Store exchange rates in the database.

        Args:
            target_currency: Target currency (EUR or USD)
            rates: Dictionary mapping base_currency -> rate
            for_date: Date of the exchange rates

        Returns:
            Number of rates stored
        """
        try:
            stored_count = 0

            # Normalize date to start of day (midnight UTC)
            rate_datetime = datetime.combine(for_date, datetime.min.time())

            for base_currency, rate in rates.items():
                # Check if rate already exists
                existing = self.db.query(ExchangeRate).filter(
                    and_(
                        ExchangeRate.date == rate_datetime,
                        ExchangeRate.base_currency == base_currency,
                        ExchangeRate.target_currency == target_currency
                    )
                ).first()

                if existing:
                    # Update existing rate
                    existing.rate = rate
                    existing.updated_at = datetime.utcnow()
                    logger.debug(f"Updated rate: {base_currency}/{target_currency} = {rate}")
                else:
                    # Create new rate
                    new_rate = ExchangeRate(
                        date=rate_datetime,
                        base_currency=base_currency,
                        target_currency=target_currency,
                        rate=rate
                    )
                    self.db.add(new_rate)
                    logger.debug(f"Stored new rate: {base_currency}/{target_currency} = {rate}")

                stored_count += 1

            self.db.commit()
            logger.info(f"Stored {stored_count} exchange rates for {target_currency} on {for_date}")
            return stored_count

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error storing exchange rates: {e}")
            raise Exception(f"Failed to store exchange rates: {e}")

    def sync_exchange_rates(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, int]:
        """
        Sync exchange rates for a date range using batch API calls.
        Processes in batches to avoid rate limits and improve efficiency.

        Args:
            start_date: Start date (defaults to January 1, 2024)
            end_date: End date (defaults to today)

        Returns:
            Dictionary with sync statistics
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = date(2024, 1, 1)  # Default to start of 2024

        logger.info(f"Syncing exchange rates from {start_date} to {end_date}")

        # Get distinct currencies from transactions for reference
        transaction_currencies = self.get_distinct_transaction_currencies()
        logger.info(f"Found {len(transaction_currencies)} distinct currencies in transactions: {transaction_currencies}")
        
        # Always use default currencies as base currencies
        # This ensures we have rates for common currencies even if they're not in transactions yet
        base_currencies = self.DEFAULT_CURRENCIES.copy()
        
        # Also include any additional currencies found in transactions that aren't in defaults
        for curr in transaction_currencies:
            if curr not in base_currencies:
                base_currencies.append(curr)
                logger.info(f"Added transaction currency {curr} to base currencies")
        
        logger.info(f"Using {len(base_currencies)} base currencies: {base_currencies}")
        
        # Target currencies are always EUR and USD (functional currencies)
        target_currencies = self.FUNCTIONAL_CURRENCIES.copy()
        logger.info(f"Target currencies (functional): {target_currencies}")

        total_stored = 0
        dates_processed = 0
        total_days = (end_date - start_date).days + 1
        failed_batches = []

        # Process in batches to avoid rate limits
        current_batch_start = start_date
        
        print(f"  Fetching rates for {len(base_currencies)} base currencies -> EUR/USD in batches of {self.BATCH_SIZE_DAYS} days...")
        
        # Process each base currency
        for base_currency in base_currencies:
            current_batch_start = start_date  # Reset for each currency
            
            # Special handling for EUR and USD: they convert to themselves at 1.0
            # AND we need to fetch cross-conversion rates (EUR->USD, USD->EUR)
            if base_currency in ["EUR", "USD"]:
                # Store 1.0 rates for EUR->EUR or USD->USD (self-conversion)
                target = base_currency
                stored_self_conversion = 0
                current_date = start_date
                while current_date <= end_date:
                    rate_datetime = datetime.combine(current_date, datetime.min.time())
                    existing = self.db.query(ExchangeRate).filter(
                        and_(
                            ExchangeRate.date == rate_datetime,
                            ExchangeRate.base_currency == base_currency,
                            ExchangeRate.target_currency == target
                        )
                    ).first()
                    
                    if not existing:
                        new_rate = ExchangeRate(
                            date=rate_datetime,
                            base_currency=base_currency,
                            target_currency=target,
                            rate=Decimal("1.0")
                        )
                        self.db.add(new_rate)
                        total_stored += 1
                        stored_self_conversion += 1
                    
                    dates_processed += 1
                    current_date += timedelta(days=1)
                
                self.db.commit()
                print(f"  {base_currency} -> {base_currency}: Stored {stored_self_conversion} rates (1.0)")
                
                # Now fetch cross-conversion rates (EUR->USD or USD->EUR)
                # Determine the other functional currency
                if base_currency == "EUR":
                    cross_target = "USD"
                elif base_currency == "USD":
                    cross_target = "EUR"
                else:
                    cross_target = None
                
                # Fetch cross-conversion rates if needed
                if cross_target:
                    current_batch_start = start_date
                    while current_batch_start <= end_date:
                        current_batch_end = min(
                            current_batch_start + timedelta(days=self.BATCH_SIZE_DAYS - 1),
                            end_date
                        )
                        
                        batch_days = (current_batch_end - current_batch_start).days + 1
                        progress = ((total_days - (end_date - current_batch_start).days) / total_days) * 100
                        
                        try:
                            print(f"  [{progress:.1f}%] {base_currency} -> {cross_target}: {current_batch_start} to {current_batch_end}...", end=" ", flush=True)
                            
                            # Fetch rates: base_currency -> cross_target
                            rates_batch = self.fetch_exchange_rates_batch(
                                base_currency, [cross_target], current_batch_start, current_batch_end
                            )
                            
                            # Store rates for each date
                            batch_stored = 0
                            for rate_date, rates in rates_batch.items():
                                if cross_target in rates:
                                    count = self.store_exchange_rates(cross_target, {base_currency: rates[cross_target]}, rate_date)
                                    batch_stored += count
                                    dates_processed += 1
                            
                            total_stored += batch_stored
                            print(f"✓ ({batch_stored} rates)")
                            
                            # Small delay between batches
                            if current_batch_start < date.today():
                                time.sleep(0.3)
                            
                        except Exception as e:
                            failed_batches.append((base_currency, current_batch_start, current_batch_end))
                            print(f"✗ Error: {e}")
                            logger.error(f"Error fetching batch {base_currency} {current_batch_start} to {current_batch_end}: {e}")
                        
                        current_batch_start = current_batch_end + timedelta(days=1)
                    
                    # Small delay between currencies
                    time.sleep(0.2)
                    continue  # Skip the regular processing below
            
            # For other currencies, fetch from API
            while current_batch_start <= end_date:
                # Calculate batch end date
                current_batch_end = min(
                    current_batch_start + timedelta(days=self.BATCH_SIZE_DAYS - 1),
                    end_date
                )
                
                batch_days = (current_batch_end - current_batch_start).days + 1
                progress = ((total_days - (end_date - current_batch_start).days) / total_days) * 100
                
                try:
                    print(f"  [{progress:.1f}%] {base_currency} -> EUR/USD: {current_batch_start} to {current_batch_end}...", end=" ", flush=True)
                    
                    # Fetch rates: base_currency -> EUR/USD
                    rates_batch = self.fetch_exchange_rates_batch(
                        base_currency, target_currencies, current_batch_start, current_batch_end
                    )
                    
                    # Store rates for each date
                    batch_stored = 0
                    for rate_date, rates in rates_batch.items():
                        # Store EUR rate
                        if "EUR" in rates:
                            count = self.store_exchange_rates("EUR", {base_currency: rates["EUR"]}, rate_date)
                            batch_stored += count
                        
                        # Store USD rate
                        if "USD" in rates:
                            count = self.store_exchange_rates("USD", {base_currency: rates["USD"]}, rate_date)
                            batch_stored += count
                        
                        dates_processed += 1
                    
                    total_stored += batch_stored
                    print(f"✓ ({batch_stored} rates)")
                    
                    # Small delay between batches to avoid rate limiting
                    if current_batch_start < date.today():
                        time.sleep(0.3)  # 300ms delay between batches
                    
                except Exception as e:
                    failed_batches.append((base_currency, current_batch_start, current_batch_end))
                    print(f"✗ Error: {e}")
                    logger.error(f"Error fetching batch {base_currency} {current_batch_start} to {current_batch_end}: {e}")
                    # Continue with next batch
                
                # Move to next batch
                current_batch_start = current_batch_end + timedelta(days=1)
            
            # Small delay between currencies
            time.sleep(0.2)
        
        print(f"  ✓ Completed: {dates_processed} dates processed, {total_stored} rates stored")
        
        if failed_batches:
            print(f"  ⚠️  Failed batches: {len(failed_batches)}")
            logger.warning(f"Failed batches: {failed_batches}")

        result = {
            "dates_processed": dates_processed,
            "total_rates_stored": total_stored,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "base_currencies": base_currencies,
            "target_currencies": target_currencies,
            "failed_batches": len(failed_batches)
        }
        
        logger.info(f"Exchange rate sync completed successfully. Result: {result}")
        return result

    def get_exchange_rate(
        self,
        base_currency: str,
        target_currency: str,
        for_date: date
    ) -> Optional[Decimal]:
        """
        Get exchange rate for a specific date.

        Args:
            base_currency: Base currency (e.g., GBP)
            target_currency: Target currency (EUR or USD)
            for_date: Date to get rate for

        Returns:
            Exchange rate or None if not found
        """
        if base_currency == target_currency:
            return Decimal("1.0")

        try:
            # Normalize date to start of day
            rate_datetime = datetime.combine(for_date, datetime.min.time())

            # Query database
            rate_record = self.db.query(ExchangeRate).filter(
                and_(
                    ExchangeRate.date == rate_datetime,
                    ExchangeRate.base_currency == base_currency,
                    ExchangeRate.target_currency == target_currency
                )
            ).first()

            if rate_record:
                return rate_record.rate

            # If not found, try to find closest date (within 7 days)
            for days_back in range(1, 8):
                past_date = rate_datetime - timedelta(days=days_back)
                rate_record = self.db.query(ExchangeRate).filter(
                    and_(
                        ExchangeRate.date == past_date,
                        ExchangeRate.base_currency == base_currency,
                        ExchangeRate.target_currency == target_currency
                    )
                ).first()

                if rate_record:
                    logger.warning(
                        f"Using rate from {days_back} days ago for {base_currency}/{target_currency}"
                    )
                    return rate_record.rate

            logger.warning(f"No exchange rate found for {base_currency}/{target_currency} on {for_date}")
            return None

        except Exception as e:
            logger.error(f"Error getting exchange rate: {e}")
            return None

    def convert_amount(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        for_date: date
    ) -> Optional[Decimal]:
        """
        Convert an amount from one currency to another.

        Args:
            amount: Amount to convert
            from_currency: Source currency
            to_currency: Target currency
            for_date: Date for exchange rate

        Returns:
            Converted amount or None if conversion failed
        """
        if from_currency == to_currency:
            return amount

        rate = self.get_exchange_rate(from_currency, to_currency, for_date)

        if rate is None:
            return None

        return amount * rate
