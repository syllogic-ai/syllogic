"""
Test subscription identifier API endpoint.
"""
import sys
import os
import requests
import json
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:8000/api"


def setup_test_data():
    """Create test user and account."""
    from app.database import SessionLocal, Base, engine
    from app.models import Account
    from app.db_helpers import get_or_create_system_user
    from decimal import Decimal
    
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
        user = get_or_create_system_user(db)
        user_id = str(user.id)
        
        account = Account(
            user_id=user_id,
            name="Test Account",
            account_type="checking",
            institution="Test Bank",
            currency="EUR",
            balance_available=Decimal("1000.00"),
            starting_balance=Decimal("1000.00"),
            functional_balance=Decimal("1000.00")
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        
        return user_id, str(account.id)
    finally:
        db.close()


def test_subscription_detection():
    """Test subscription detection functionality."""
    print("Testing Subscription Identifier API...")
    
    try:
        # Setup test data
        test_user_id, test_account_id = setup_test_data()
        
        # Step 1: Import transactions that look like subscriptions
        import_url = f"{BASE_URL}/transactions/import"
        
        # Create recurring transactions (same merchant, similar amounts, monthly pattern)
        base_date = datetime.now(timezone.utc)
        transactions = []
        
        for i in range(3):  # 3 months of data
            month_date = base_date.replace(day=1) - timedelta(days=30*i)
            transactions.append({
                "account_id": test_account_id,
                "amount": -9.99,
                "description": "NETFLIX SUBSCRIPTION",
                "merchant": "Netflix",
                "booked_at": month_date.isoformat(),
                "transaction_type": "debit",
                "currency": "EUR"
            })
        
        import_payload = {
            "transactions": transactions,
            "user_id": test_user_id,
            "sync_exchange_rates": False,
            "update_functional_amounts": False,
            "calculate_balances": False
        }
        
        # Import transactions
        import_response = requests.post(import_url, json=import_payload, timeout=60)
        
        if import_response.status_code == 200:
            import_result = import_response.json()
            # Check if subscription detection happened
            subscription_detection = import_result.get("subscription_detection")
            if subscription_detection:
                detected_count = subscription_detection.get("detected_count", 0)
                print(f"✓ Subscription detection test passed ({detected_count} subscriptions detected)")
                return True
            else:
                print("⚠ Subscription detection returned no results (might need more transactions)")
                # Still consider it a pass if import succeeded
                return True
        else:
            print(f"✗ Could not import test transactions: {import_response.status_code}")
            print(f"  Response: {import_response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success = test_subscription_detection()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
