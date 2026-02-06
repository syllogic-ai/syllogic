"""
Test transaction import API endpoint.
"""
import sys
import os
import requests
import json
from uuid import uuid4
from datetime import datetime, timezone
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine
from app.models import User, Account, Category
from app.db_helpers import get_or_create_system_user

BASE_URL = "http://localhost:8000/api"


def setup_test_data():
    """Create test user, account, and categories."""
    db = SessionLocal()
    try:
        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        
        # Get or create system user
        user = get_or_create_system_user(db)
        user_id = str(user.id)
        
        # Create a test account
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
        
        # Create test categories
        categories = [
            Category(user_id=user_id, name="Groceries", category_type="expense", is_system=False),
            Category(user_id=user_id, name="Salary", category_type="income", is_system=False),
        ]
        for cat in categories:
            db.add(cat)
        db.commit()
        
        return user_id, str(account.id)
    finally:
        db.close()


def test_transaction_import():
    """Test that transaction import API works correctly."""
    print("Testing Transaction Import API...")
    
    try:
        # Setup test data
        user_id, account_id = setup_test_data()
        
        # Test transaction import
        url = f"{BASE_URL}/transactions/import"
        
        payload = {
            "transactions": [
                {
                    "account_id": account_id,
                    "amount": -25.50,
                    "description": "TESCO SUPERMARKET",
                    "merchant": "Tesco",
                    "booked_at": datetime.now(timezone.utc).isoformat(),
                    "transaction_type": "debit",
                    "currency": "EUR"
                },
                {
                    "account_id": account_id,
                    "amount": 100.00,
                    "description": "SALARY PAYMENT",
                    "merchant": "Employer",
                    "booked_at": datetime.now(timezone.utc).isoformat(),
                    "transaction_type": "credit",
                    "currency": "EUR"
                }
            ],
            "user_id": user_id,
            "sync_exchange_rates": False,
            "update_functional_amounts": False,
            "calculate_balances": False
        }
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            assert result.get("success") == True, "Import should succeed"
            assert result.get("transactions_inserted", 0) == 2, "Should import 2 transactions"
            print(f"✓ Transaction Import API test passed ({result.get('transactions_inserted')} transactions imported)")
            return True
        else:
            print(f"✗ Transaction Import API test failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Test setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success = test_transaction_import()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
