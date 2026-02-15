"""
Test categorizer API endpoint.
"""
import sys
import os
import requests
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine
from app.models import Account, Category
from app.db_helpers import get_or_create_system_user
from tests.internal_auth import build_internal_auth_headers

BASE_URL = "http://localhost:8000/api"


def setup_test_data():
    """Create test user, account, and categories."""
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
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
        
        # Create test categories
        categories = [
            Category(user_id=user_id, name="Groceries", category_type="expense", is_system=False),
            Category(user_id=user_id, name="Transport", category_type="expense", is_system=False),
            Category(user_id=user_id, name="Salary", category_type="income", is_system=False),
        ]
        for cat in categories:
            db.add(cat)
        db.commit()
        
        return user_id
    finally:
        db.close()


def test_categorizer_single():
    """Test single transaction categorization."""
    print("Testing Categorizer API (single transaction)...")
    
    try:
        user_id = setup_test_data()
        url = f"{BASE_URL}/categories/categorize"
        path_with_query = "/api/categories/categorize"
        
        payload = {
            "description": "TESCO SUPERMARKET",
            "merchant": "Tesco",
            "amount": -25.50,
            "transaction_type": "debit",
            "use_llm": False  # Use deterministic matching for faster tests
        }
        
        response = requests.post(
            url,
            json=payload,
            headers=build_internal_auth_headers("POST", path_with_query, user_id),
            timeout=30,
        )
    
        if response.status_code == 200:
            result = response.json()
            # Should return a category (or None if no match)
            assert "category_id" in result or result.get("category_id") is None
            assert "method" in result
            print(f"✓ Single categorization test passed (method: {result.get('method')})")
            return True
        else:
            print(f"✗ Single categorization test failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Test setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_categorizer_batch():
    """Test batch transaction categorization."""
    print("Testing Categorizer API (batch)...")
    
    try:
        user_id = setup_test_data()
        url = f"{BASE_URL}/categories/categorize/batch"
        path_with_query = "/api/categories/categorize/batch"
        
        payload = {
            "transactions": [
                {
                    "description": "TESCO SUPERMARKET",
                    "merchant": "Tesco",
                    "amount": -25.50,
                    "transaction_type": "debit"
                },
                {
                    "description": "UBER RIDE",
                    "merchant": "Uber",
                    "amount": -15.00,
                    "transaction_type": "debit"
                },
                {
                    "description": "SALARY PAYMENT",
                    "merchant": "Employer",
                    "amount": 100.00,
                    "transaction_type": "credit"
                }
            ],
            "use_llm": False  # Use deterministic matching for faster tests
        }
        
        response = requests.post(
            url,
            json=payload,
            headers=build_internal_auth_headers("POST", path_with_query, user_id),
            timeout=30,
        )
    
        if response.status_code == 200:
            result = response.json()
            assert "results" in result
            assert len(result["results"]) == 3, "Should return 3 results"
            assert result.get("total_transactions") == 3
            print(f"✓ Batch categorization test passed ({result.get('categorized_count', 0)} categorized)")
            return True
        else:
            print(f"✗ Batch categorization test failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Test setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success1 = test_categorizer_single()
        success2 = test_categorizer_batch()
        sys.exit(0 if (success1 and success2) else 1)
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
