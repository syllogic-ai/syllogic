"""
Example script to test the transaction import endpoint.
This script demonstrates how to use the POST /api/transactions/import endpoint.

Run with: python -m app.routes.test_transaction_import_example (from the backend directory)
Or: cd backend && python -m app.routes.test_transaction_import_example
"""
import httpx
import json
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

# Base URL for your API
BASE_URL = "http://localhost:8000/api"


def test_transaction_import():
    """Test the transaction import endpoint with example transactions."""
    print("\n" + "=" * 70)
    print("TESTING TRANSACTION IMPORT ENDPOINT")
    print("=" * 70)

    # Example transactions - you'll need to replace account_id with a real one
    # First, let's get a real account ID (this is a helper - you should use your actual account ID)
    print("\n📋 Example Transactions:")
    print("   Note: Replace 'YOUR_ACCOUNT_ID' with an actual account ID from your database")
    
    # Example transactions with various scenarios
    example_transactions = [
        {
            "account_id": "YOUR_ACCOUNT_ID",  # Replace with actual UUID
            "amount": Decimal("25.50"),
            "description": "TESCO SUPERMARKET",
            "merchant": "Tesco",
            "booked_at": (datetime.now() - timedelta(days=5)).isoformat(),
            "transaction_type": "debit",
            "currency": "EUR"
        },
        {
            "account_id": "YOUR_ACCOUNT_ID",
            "amount": Decimal("15.00"),
            "description": "UBER RIDE",
            "merchant": "Uber",
            "booked_at": (datetime.now() - timedelta(days=4)).isoformat(),
            "transaction_type": "debit",
            "currency": "EUR"
        },
        {
            "account_id": "YOUR_ACCOUNT_ID",
            "amount": Decimal("3000.00"),
            "description": "SALARY PAYMENT",
            "merchant": "ACME Corp",
            "booked_at": (datetime.now() - timedelta(days=1)).isoformat(),
            "transaction_type": "credit",
            "currency": "EUR"
        },
        {
            "account_id": "YOUR_ACCOUNT_ID",
            "amount": Decimal("50.00"),
            "description": "AMAZON PURCHASE",
            "merchant": "Amazon",
            "booked_at": datetime.now().isoformat(),
            "transaction_type": "debit",
            "currency": "USD",
            "external_id": "ext-12345"
        },
        {
            "account_id": "YOUR_ACCOUNT_ID",
            "amount": Decimal("100.00"),
            "description": "RESTAURANT DINNER",
            "merchant": "Fine Dining Restaurant",
            "booked_at": (datetime.now() - timedelta(days=2)).isoformat(),
            "transaction_type": "debit",
            "currency": "GBP"
        }
    ]
    
    # Convert Decimal to string for JSON serialization
    payload_transactions = []
    for txn in example_transactions:
        payload_txn = {
            "account_id": str(txn["account_id"]),
            "amount": str(txn["amount"]),
            "description": txn["description"],
            "merchant": txn["merchant"],
            "booked_at": txn["booked_at"],
            "transaction_type": txn["transaction_type"],
            "currency": txn["currency"]
        }
        if "external_id" in txn:
            payload_txn["external_id"] = txn["external_id"]
        payload_transactions.append(payload_txn)
    
    payload = {
        "transactions": payload_transactions,
        "sync_exchange_rates": True,
        "update_functional_amounts": True,
        "calculate_balances": True
    }
    
    url = f"{BASE_URL}/transactions/import"
    
    print(f"\nRequest: POST {url}")
    print(f"Payload: {json.dumps(payload, indent=2, default=str)}")
    
    try:
        print("\n⏳ Sending request...")
        response = httpx.post(url, json=payload, timeout=300.0)  # 5 min timeout
        response.raise_for_status()
        
        result = response.json()
        print(f"\n✅ Response ({response.status_code}):")
        print(json.dumps(result, indent=2, default=str))
        
        # Pretty print summary
        print("\n" + "=" * 70)
        print("📊 IMPORT SUMMARY")
        print("=" * 70)
        print(f"✅ Transactions inserted: {result.get('transactions_inserted', 0)}")
        
        if result.get('categorization_summary'):
            cat_summary = result['categorization_summary']
            print(f"\n📁 Categorization:")
            print(f"   Total: {cat_summary.get('total', 0)}")
            print(f"   ✅ Categorized: {cat_summary.get('categorized', 0)}")
            print(f"   🔍 Deterministic: {cat_summary.get('deterministic', 0)}")
            print(f"   🤖 LLM: {cat_summary.get('llm', 0)}")
            print(f"   ❓ Uncategorized: {cat_summary.get('uncategorized', 0)}")
            if cat_summary.get('tokens_used', 0) > 0:
                print(f"   💰 Tokens used: {cat_summary.get('tokens_used', 0)}")
                print(f"   💵 Cost: ${cat_summary.get('cost_usd', 0):.6f}")
        
        if result.get('exchange_rates_synced'):
            rates = result['exchange_rates_synced']
            if 'error' in rates:
                print(f"\n⚠️  Exchange Rates: Error - {rates['error']}")
            else:
                print(f"\n💱 Exchange Rates:")
                print(f"   Dates processed: {rates.get('dates_processed', 0)}")
                print(f"   Rates stored: {rates.get('total_rates_stored', 0)}")
        
        if result.get('functional_amounts_updated'):
            func_amounts = result['functional_amounts_updated']
            if 'error' in func_amounts:
                print(f"\n⚠️  Functional Amounts: Error - {func_amounts['error']}")
            else:
                print(f"\n💰 Functional Amounts:")
                print(f"   ✅ Updated: {func_amounts.get('updated', 0)}")
                print(f"   ⏭️  Skipped: {func_amounts.get('skipped', 0)}")
                print(f"   ❌ Failed: {func_amounts.get('failed', 0)}")
        
        if result.get('balances_calculated'):
            balances = result['balances_calculated']
            if 'error' in balances:
                print(f"\n⚠️  Balances: Error - {balances['error']}")
            else:
                print(f"\n💳 Account Balances:")
                print(f"   ✅ Accounts updated: {balances.get('accounts_updated', 0)}")
        
        print("\n" + "=" * 70)
        
        return result
        
    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP Error ({e.response.status_code}):")
        try:
            error_detail = e.response.json()
            print(f"   {json.dumps(error_detail, indent=2)}")
        except:
            print(f"   {e.response.text}")
        return None
    except httpx.RequestError as e:
        print(f"\n❌ Request Error: {e}")
        print(f"   Make sure the FastAPI server is running: cd backend && uvicorn app.main:app --reload")
        return None
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_or_create_account_id(api_url: str = BASE_URL):
    """Get an account ID or create one if needed."""
    print("\n" + "=" * 70)
    print("GETTING/CREATING ACCOUNT")
    print("=" * 70)
    
    # Try to get account via API first
    url = f"{api_url}/accounts/"
    
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        
        accounts = response.json()
        if accounts:
            print(f"\n✅ Found {len(accounts)} account(s):")
            for acc in accounts[:3]:  # Show first 3
                print(f"   • {acc.get('name', 'N/A')} (ID: {acc.get('id')})")
            return accounts[0].get('id') if accounts else None
    except httpx.RequestError:
        print("\n⚠️  API server not running. Creating account directly in database...")
        # Fall back to direct database access
        return _create_account_direct()
    except Exception as e:
        print(f"\n⚠️  Error getting accounts via API: {e}")
        print("   Falling back to direct database access...")
        return _create_account_direct()
    
    # No accounts found via API, try to create one
    print("\n⚠️  No accounts found. Creating a new account...")
    return _create_account_via_api(api_url) or _create_account_direct()


def _create_account_via_api(api_url: str = BASE_URL):
    """Create an account via API."""
    url = f"{api_url}/accounts/"
    payload = {
        "name": "Test Account",
        "account_type": "checking",
        "institution": "Test Bank",
        "currency": "EUR",
    }
    
    try:
        print("   Creating account via API...")
        response = httpx.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        
        account = response.json()
        account_id = account.get('id')
        print(f"   ✅ Created account '{account.get('name')}' (ID: {account_id})")
        return account_id
    except Exception as e:
        print(f"   ⚠️  Failed to create account via API: {e}")
        return None


def _create_account_direct():
    """Create an account directly in the database."""
    try:
        import sys
        from pathlib import Path
        
        # Add parent directory to path
        backend_dir = Path(__file__).parent.parent.parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        
        from app.database import SessionLocal
        from app.models import Account
        from app.db_helpers import get_or_create_system_user
        
        db = SessionLocal()
        try:
            # Example script fallback: ensure a local test user exists.
            user = get_or_create_system_user(db)
            user_id = str(user.id)
            
            # Check if account already exists
            existing_account = db.query(Account).filter(
                Account.user_id == user_id,
                Account.name == "Test Account"
            ).first()
            
            if existing_account:
                print(f"   ✅ Found existing account '{existing_account.name}' (ID: {existing_account.id})")
                return str(existing_account.id)
            
            # Create new account
            account = Account(
                user_id=user_id,
                name="Test Account",
                account_type="checking",
                institution="Test Bank",
                currency="EUR",
                starting_balance=0
            )
            
            db.add(account)
            db.commit()
            db.refresh(account)
            
            print(f"   ✅ Created account '{account.name}' (ID: {account.id})")
            return str(account.id)
        finally:
            db.close()
    except Exception as e:
        print(f"   ❌ Failed to create account directly: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test the transaction import endpoint"
    )
    parser.add_argument(
        "--account-id",
        type=str,
        help="Account ID to use for transactions (if not provided, will try to fetch one)"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=BASE_URL,
        help=f"Base URL for the API (default: {BASE_URL})"
    )
    parser.add_argument(
        "--skip-rates",
        action="store_true",
        help="Skip exchange rate syncing"
    )
    parser.add_argument(
        "--skip-functional",
        action="store_true",
        help="Skip functional amount updates"
    )
    parser.add_argument(
        "--skip-balances",
        action="store_true",
        help="Skip balance calculation"
    )
    
    args = parser.parse_args()
    
    # Update BASE_URL if custom URL provided
    api_url = args.api_url
    
    # Get account ID if not provided
    account_id = args.account_id
    if not account_id:
        print("No account ID provided. Attempting to get or create one...")
        account_id = get_or_create_account_id(api_url)
        if not account_id:
            print("\n❌ Cannot proceed without an account ID.")
            print("   Please ensure:")
            print("   1. Database is accessible")
            print("   2. User exists in the database")
            print("   3. Or use --account-id flag with an existing account ID")
            return
    
    print(f"\n✅ Using account ID: {account_id}")
    
    # Update example transactions with real account ID
    example_transactions = [
        {
            "account_id": account_id,
            "amount": Decimal("25.50"),
            "description": "TESCO SUPERMARKET",
            "merchant": "Tesco",
            "booked_at": (datetime.now() - timedelta(days=5)).isoformat(),
            "transaction_type": "debit",
            "currency": "EUR"
        },
        {
            "account_id": account_id,
            "amount": Decimal("15.00"),
            "description": "UBER RIDE",
            "merchant": "Uber",
            "booked_at": (datetime.now() - timedelta(days=4)).isoformat(),
            "transaction_type": "debit",
            "currency": "EUR"
        },
        {
            "account_id": account_id,
            "amount": Decimal("3000.00"),
            "description": "SALARY PAYMENT",
            "merchant": "ACME Corp",
            "booked_at": (datetime.now() - timedelta(days=1)).isoformat(),
            "transaction_type": "credit",
            "currency": "EUR"
        },
        {
            "account_id": account_id,
            "amount": Decimal("50.00"),
            "description": "AMAZON PURCHASE",
            "merchant": "Amazon",
            "booked_at": datetime.now().isoformat(),
            "transaction_type": "debit",
            "currency": "USD",
            "external_id": "ext-test-12345"
        },
        {
            "account_id": account_id,
            "amount": Decimal("100.00"),
            "description": "RESTAURANT DINNER",
            "merchant": "Fine Dining Restaurant",
            "booked_at": (datetime.now() - timedelta(days=2)).isoformat(),
            "transaction_type": "debit",
            "currency": "GBP"
        },
        {
            "account_id": account_id,
            "amount": Decimal("75.25"),
            "description": "GYM MEMBERSHIP",
            "merchant": "Fitness World",
            "booked_at": (datetime.now() - timedelta(days=10)).isoformat(),
            "transaction_type": "debit",
            "currency": "EUR"
        },
        {
            "account_id": account_id,
            "amount": Decimal("350.00"),
            "description": "ELECTRICITY BILL",
            "merchant": "Energy Provider",
            "booked_at": (datetime.now() - timedelta(days=11)).isoformat(),
            "transaction_type": "debit",
            "currency": "EUR"
        },
        {
            "account_id": account_id,
            "amount": Decimal("1500.00"),
            "description": "INVESTMENT DIVIDEND",
            "merchant": "Investment Fund",
            "booked_at": (datetime.now() - timedelta(days=12)).isoformat(),
            "transaction_type": "credit",
            "currency": "EUR"
        },
        {
            "account_id": account_id,
            "amount": Decimal("32.80"),
            "description": "PHARMACY PURCHASE",
            "merchant": "Boots Pharmacy",
            "booked_at": (datetime.now() - timedelta(days=13)).isoformat(),
            "transaction_type": "debit",
            "currency": "EUR"
        },
        {
            "account_id": account_id,
            "amount": Decimal("200.00"),
            "description": "CONCERT TICKETS",
            "merchant": "Ticketmaster",
            "booked_at": (datetime.now() - timedelta(days=14)).isoformat(),
            "transaction_type": "debit",
            "currency": "USD"
        }
    ]
    
    # Convert Decimal to string for JSON serialization
    payload_transactions = []
    for txn in example_transactions:
        payload_txn = {
            "account_id": str(txn["account_id"]),
            "amount": str(txn["amount"]),
            "description": txn["description"],
            "merchant": txn["merchant"],
            "booked_at": txn["booked_at"],
            "transaction_type": txn["transaction_type"],
            "currency": txn["currency"]
        }
        if "external_id" in txn:
            payload_txn["external_id"] = txn["external_id"]
        payload_transactions.append(payload_txn)
    
    payload = {
        "transactions": payload_transactions,
        "sync_exchange_rates": not args.skip_rates,
        "update_functional_amounts": not args.skip_functional,
        "calculate_balances": not args.skip_balances
    }
    
    url = f"{BASE_URL}/transactions/import"
    
    print(f"\nRequest: POST {url}")
    print(f"Payload preview:")
    print(f"   Transactions: {len(payload_transactions)}")
    print(f"   Sync exchange rates: {payload['sync_exchange_rates']}")
    print(f"   Update functional amounts: {payload['update_functional_amounts']}")
    print(f"   Calculate balances: {payload['calculate_balances']}")
    
    try:
        print("\n⏳ Sending request (this may take a few minutes for exchange rate syncing)...")
        response = httpx.post(url, json=payload, timeout=300.0)  # 5 min timeout
        response.raise_for_status()
        
        result = response.json()
        print(f"\n✅ Response ({response.status_code}):")
        
        # Pretty print summary
        print("\n" + "=" * 70)
        print("📊 IMPORT SUMMARY")
        print("=" * 70)
        print(f"✅ Transactions inserted: {result.get('transactions_inserted', 0)}")
        print(f"📝 Message: {result.get('message', 'N/A')}")
        
        if result.get('categorization_summary'):
            cat_summary = result['categorization_summary']
            print(f"\n📁 Categorization:")
            print(f"   Total: {cat_summary.get('total', 0)}")
            print(f"   ✅ Categorized: {cat_summary.get('categorized', 0)}")
            print(f"   🔍 Deterministic: {cat_summary.get('deterministic', 0)}")
            print(f"   🤖 LLM: {cat_summary.get('llm', 0)}")
            print(f"   ❓ Uncategorized: {cat_summary.get('uncategorized', 0)}")
            if cat_summary.get('tokens_used', 0) > 0:
                print(f"   💰 Tokens used: {cat_summary.get('tokens_used', 0)}")
                print(f"   💵 Cost: ${cat_summary.get('cost_usd', 0):.6f}")
        
        if result.get('exchange_rates_synced'):
            rates = result['exchange_rates_synced']
            if 'error' in rates:
                print(f"\n⚠️  Exchange Rates: Error - {rates['error']}")
            else:
                print(f"\n💱 Exchange Rates:")
                print(f"   Dates processed: {rates.get('dates_processed', 0)}")
                print(f"   Rates stored: {rates.get('total_rates_stored', 0)}")
                if rates.get('base_currencies'):
                    print(f"   Base currencies: {', '.join(rates.get('base_currencies', []))}")
        
        if result.get('functional_amounts_updated'):
            func_amounts = result['functional_amounts_updated']
            if 'error' in func_amounts:
                print(f"\n⚠️  Functional Amounts: Error - {func_amounts['error']}")
            else:
                print(f"\n💰 Functional Amounts:")
                print(f"   ✅ Updated: {func_amounts.get('updated', 0)}")
                print(f"   ⏭️  Skipped: {func_amounts.get('skipped', 0)}")
                print(f"   ❌ Failed: {func_amounts.get('failed', 0)}")
        
        if result.get('balances_calculated'):
            balances = result['balances_calculated']
            if 'error' in balances:
                print(f"\n⚠️  Balances: Error - {balances['error']}")
            else:
                print(f"\n💳 Account Balances:")
                print(f"   ✅ Accounts updated: {balances.get('accounts_updated', 0)}")
        
        print("\n" + "=" * 70)
        print("\n✅ Import completed successfully!")
        
        # Verify transactions were actually inserted
        if result.get('transaction_ids'):
            print(f"\n🔍 Verification: Transaction IDs inserted:")
            for txn_id in result['transaction_ids'][:5]:  # Show first 5
                print(f"   • {txn_id}")
            
            # Try to fetch one transaction to verify
            if result['transaction_ids']:
                verify_url = f"{api_url}/transactions/{result['transaction_ids'][0]}"
                try:
                    verify_response = httpx.get(verify_url, timeout=10.0)
                    if verify_response.status_code == 200:
                        verify_txn = verify_response.json()
                        print(f"\n✅ Verified transaction exists:")
                        print(f"   Description: {verify_txn.get('description', 'N/A')}")
                        print(f"   Amount: {verify_txn.get('amount', 'N/A')}")
                        print(f"   Category: {verify_txn.get('category_system_id', 'N/A')}")
                except:
                    pass  # Verification failed, but that's okay
        
        return result
        
    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP Error ({e.response.status_code}):")
        try:
            error_detail = e.response.json()
            print(f"   {json.dumps(error_detail, indent=2)}")
        except:
            print(f"   {e.response.text}")
        return None
    except httpx.RequestError as e:
        print(f"\n❌ Request Error: {e}")
        print(f"   Make sure the FastAPI server is running:")
        print(f"   cd backend && uvicorn app.main:app --reload")
        return None
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    main()
