"""
Simple script to show Kraken account balances.
"""
import os
from dotenv import load_dotenv
from app.integrations.kraken_adapter import KrakenAdapter

# Load environment variables
load_dotenv()


def main():
    # Get API credentials
    api_key = os.getenv("KRAKEN_API_KEY")
    private_key = os.getenv("KRAKEN_PRIVATE_KEY")

    if not api_key or not private_key:
        print("❌ Error: KRAKEN_API_KEY and KRAKEN_PRIVATE_KEY not found in .env file")
        print("\nGet your API keys from: https://www.kraken.com/u/security/api")
        return

    print("💰 Fetching Kraken balances...\n")

    adapter = KrakenAdapter(api_key=api_key, private_key=private_key)

    # Get balances
    balances = adapter.get_account_balance()

    print("=" * 50)
    print("KRAKEN ACCOUNT BALANCES")
    print("=" * 50)

    if balances:
        # Calculate total in various currencies (simplified)
        total_count = 0

        for asset, balance in sorted(balances.items()):
            if balance > 0:  # Only show non-zero balances
                normalized_asset = adapter._normalize_asset_name(asset)
                print(f"{normalized_asset:10} {balance:>20,.8f}")
                total_count += 1

        print("=" * 50)
        print(f"Total assets with balance: {total_count}")
    else:
        print("No balances found")
        print("=" * 50)


if __name__ == "__main__":
    main()
