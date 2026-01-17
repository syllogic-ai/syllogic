"""
Example usage of Kraken adapter.

This example demonstrates:
1. Connecting to Kraken
2. Fetching account balances
3. Fetching transaction history (deposits, withdrawals, trades)
4. Saving transactions to CSV

Before running:
1. Create API keys at: https://www.kraken.com/u/security/api
2. Required permissions: Query Funds, Query Open Orders & Trades, Query Closed Orders & Trades
3. Add keys to .env file as KRAKEN_API_KEY and KRAKEN_PRIVATE_KEY

Rate Limiting:
- Kraken has tiered rate limits (Starter: 15, Intermediate: 20, Pro: 20 max API counter)
- This script adds delays to respect Starter tier limits (most conservative)
"""
import os
import csv
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from app.integrations.kraken_adapter import KrakenAdapter

# Load environment variables
load_dotenv()

# Rate limit configuration
# Kraken uses a "leaky bucket" rate limiting system:
# - Starter: Max 15 counter, -0.33/sec decay
# - Intermediate: Max 20 counter, -0.5/sec decay
# - Pro: Max 20 counter, -1/sec decay
#
# Adjust API_CALL_DELAY based on your tier:
# - Starter: 3.0 seconds (recommended, most conservative)
# - Intermediate: 2.0 seconds
# - Pro: 1.0 seconds
API_CALL_DELAY = 4.5  # seconds between API calls


def main():
    """Example usage of Kraken adapter."""

    # Get API credentials
    api_key = os.getenv("KRAKEN_API_KEY")
    private_key = os.getenv("KRAKEN_PRIVATE_KEY")

    if not api_key or not private_key:
        print("❌ Error: KRAKEN_API_KEY and KRAKEN_PRIVATE_KEY not found in .env file")
        print("\nTo get your API keys:")
        print("1. Go to: https://www.kraken.com/u/security/api")
        print("2. Create a new API key with these permissions:")
        print("   - Query Funds")
        print("   - Query Open Orders & Trades")
        print("   - Query Closed Orders & Trades")
        print("3. Add to .env file:")
        print("   KRAKEN_API_KEY=your_api_key")
        print("   KRAKEN_PRIVATE_KEY=your_private_key")
        return

    print("🔐 Initializing Kraken adapter...")
    adapter = KrakenAdapter(api_key=api_key, private_key=private_key)
    print("✓ Connected to Kraken\n")

    # Fetch all accounts
    print("=" * 70)
    print("Fetching Accounts")
    print("=" * 70)
    print(f"⏱️  Rate limit: {API_CALL_DELAY}s delay between API calls")
    try:
        accounts = adapter.fetch_accounts()
        print(f"✓ Fetched accounts")

        # Rate limit delay after API call
        time.sleep(API_CALL_DELAY)

        if accounts:
            print(f"\nFound {len(accounts)} account(s) with non-zero balance:\n")

            for i, account in enumerate(accounts, 1):
                print(f"{i}. {account.name}")
                print(f"   Currency: {account.currency}")
                print(f"   Functional Balance: {account.functional_balance}")
                print()

        else:
            print("No accounts with non-zero balance found")
            return

    except Exception as e:
        print(f"❌ Error fetching accounts: {e}")
        return

    # Fetch transactions for ALL accounts in 3-month windows
    print("=" * 70)
    print("Fetching ALL Transactions from ALL Accounts")
    print("=" * 70)

    # Create 3-month windows from Feb 2024 to today
    # This is necessary because Kraken limits to ~50 trades per API call
    overall_start = datetime(2024, 2, 1)
    overall_end = datetime.now()

    # Generate 3-month windows
    windows = []
    current_start = overall_start

    while current_start < overall_end:
        # Calculate 3 months ahead
        current_end = current_start + timedelta(days=90)  # Approximately 3 months
        if current_end > overall_end:
            current_end = overall_end

        windows.append((current_start, current_end))
        current_start = current_end

    print(f"📅 Overall date range: {overall_start.strftime('%Y-%m-%d')} to {overall_end.strftime('%Y-%m-%d')}")
    print(f"🔄 Fetching in {len(windows)} window(s) of ~3 months each (to avoid API limits)")
    print(f"📋 Including: Deposits, Withdrawals, Trades, Staking, Transfers, and all other ledger types")

    total_api_calls = len(accounts) * len(windows)
    estimated_time = total_api_calls * API_CALL_DELAY

    print(f"⚠️  Total API calls: {total_api_calls} ({len(accounts)} accounts × {len(windows)} windows)")
    print(f"⏱️  Estimated time: {estimated_time:.0f} seconds (~{estimated_time/60:.1f} minutes)\n")

    all_transactions = []

    # Iterate through each account
    for account_idx, account in enumerate(accounts, 1):
        print(f"\n{'='*70}")
        print(f"📊 ACCOUNT [{account_idx}/{len(accounts)}]: {account.name}")
        print(f"{'='*70}")

        account_transactions = []

        # Fetch transactions for each time window
        for window_idx, (window_start, window_end) in enumerate(windows, 1):
            print(f"\n   📆 Window [{window_idx}/{len(windows)}]: {window_start.strftime('%Y-%m-%d')} to {window_end.strftime('%Y-%m-%d')}")

            try:
                # Fetch ALL ledger types: deposits, withdrawals, trades, staking, transfers, etc.
                # No ledger_type filter is applied, so all transaction types are included
                transactions = adapter.fetch_transactions(
                    account_external_id=account.external_id,
                    start_date=window_start,
                    end_date=window_end
                )

                if transactions:
                    print(f"      ✓ Found {len(transactions)} transaction(s)")
                    account_transactions.extend(transactions)
                    all_transactions.extend(transactions)
                else:
                    print(f"      ℹ️  No transactions found")

                # Rate limit delay after each API call
                # Calculate if this is the last call
                is_last_window = (window_idx == len(windows))
                is_last_account = (account_idx == len(accounts))
                is_final_call = is_last_window and is_last_account

                if not is_final_call:
                    print(f"      ⏱️  Waiting {API_CALL_DELAY}s for rate limit...")
                    time.sleep(API_CALL_DELAY)

            except Exception as e:
                print(f"      ❌ Error: {e}")
                # Still wait even on error to avoid rapid-fire requests
                if not (window_idx == len(windows) and account_idx == len(accounts)):
                    time.sleep(API_CALL_DELAY)

        # Summary for this account
        print(f"\n   📊 Total for {account.name}: {len(account_transactions)} transaction(s)")

    print(f"\n{'='*70}")
    print(f"✅ FETCHING COMPLETE - Total transactions fetched: {len(all_transactions)}")
    print(f"{'='*70}")

    # Remove duplicates (in case any transactions appear in multiple windows)
    print("\n🔍 Removing duplicates...")
    unique_transactions = {}
    for txn in all_transactions:
        # Use transaction_id as unique key
        if txn.external_id not in unique_transactions:
            unique_transactions[txn.external_id] = txn

    all_transactions = list(unique_transactions.values())
    print(f"✓ Unique transactions: {len(all_transactions)}")

    # Display all transactions sorted by date
    print("\n" + "=" * 70)
    print(f"ALL TRANSACTIONS ({len(all_transactions)} total)")
    print("=" * 70)

    if all_transactions:
        # Sort by date (most recent first)
        all_transactions.sort(key=lambda x: x.booked_at, reverse=True)

        # Save to CSV
        date_range = f"{overall_start.strftime('%Y%m%d')}_to_{overall_end.strftime('%Y%m%d')}"
        csv_filename = f"kraken_transactions_{date_range}.csv"

        print(f"\n💾 Saving transactions to {csv_filename}...")

        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            # Define all possible columns
            fieldnames = [
                'transaction_id',
                'account_external_id',
                'account_name',
                'date',
                'timestamp',
                'description',
                'amount',
                'currency',
                'transaction_type',
                'merchant',
                'pending',
                'ledger_type',
                'refid',
                'fee',
                'balance_after',
                'asset_kraken_name',
            ]

            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for txn in all_transactions:
                # Find the account name
                account_name = ""
                for acc in accounts:
                    if acc.external_id == txn.account_external_id:
                        account_name = acc.name
                        break

                # Write row with all available data
                writer.writerow({
                    'transaction_id': txn.external_id,
                    'account_external_id': txn.account_external_id,
                    'account_name': account_name,
                    'date': txn.booked_at.strftime('%Y-%m-%d'),
                    'timestamp': txn.booked_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'description': txn.description,
                    'amount': str(txn.amount),
                    'currency': txn.currency,
                    'transaction_type': txn.transaction_type,
                    'merchant': txn.merchant or '',
                    'pending': str(txn.pending),
                    'ledger_type': txn.metadata.get('ledger_type', ''),
                    'refid': txn.metadata.get('refid', ''),
                    'fee': txn.metadata.get('fee', ''),
                    'balance_after': txn.metadata.get('balance', ''),
                    'asset_kraken_name': txn.metadata.get('asset', ''),
                })

        print(f"✅ Saved {len(all_transactions)} transactions to {csv_filename}")

        # Breakdown by transaction type
        print("\n" + "=" * 70)
        print("TRANSACTION BREAKDOWN BY TYPE")
        print("=" * 70)

        type_counts = {}
        for txn in all_transactions:
            ledger_type = txn.metadata.get('ledger_type', 'unknown')
            type_counts[ledger_type] = type_counts.get(ledger_type, 0) + 1

        for ledger_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(all_transactions)) * 100
            print(f"{ledger_type.capitalize():20} {count:>6} ({percentage:>5.1f}%)")

        # Display sample transactions
        print("\n" + "=" * 70)
        print(f"SAMPLE TRANSACTIONS (showing first 10 of {len(all_transactions)})")
        print("=" * 70)

        for i, txn in enumerate(all_transactions[:10], 1):
            print(f"\n{i}. {txn.description}")
            print(f"   Account: {txn.currency}")
            print(f"   Amount: {txn.amount} {txn.currency}")
            print(f"   Type: {txn.transaction_type} | Ledger Type: {txn.metadata.get('ledger_type', 'N/A')}")
            print(f"   Date: {txn.booked_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if txn.metadata.get("fee"):
                print(f"   Fee: {txn.metadata['fee']} {txn.currency}")

        if len(all_transactions) > 10:
            print(f"\n... and {len(all_transactions) - 10} more transactions (see CSV file)")
    else:
        print("No transactions found")

    print("\n" + "=" * 70)
    print("✅ Complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
