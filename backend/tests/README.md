# Backend API Tests

This directory contains integration tests for the backend API endpoints.

## Running Tests Locally

### Prerequisites
1. PostgreSQL and Redis must be running
2. Backend server must be running on `http://localhost:8000`
3. `INTERNAL_AUTH_SECRET` must be set (tests generate signed internal auth headers)

### Setup
```bash
cd backend
pip install -r requirements.txt
```

### Run Tests

```bash
# Start the backend server first
export INTERNAL_AUTH_SECRET=test-internal-auth-secret
uvicorn app.main:app --host 0.0.0.0 --port 8000

# In another terminal, run tests
export INTERNAL_AUTH_SECRET=test-internal-auth-secret
python tests/test_transaction_import.py
python tests/test_categorizer.py
python tests/test_subscription_identifier.py
```

## Test Files

- `test_transaction_import.py` - Tests the transaction import API endpoint
- `test_categorizer.py` - Tests the categorization API (single and batch)
- `test_subscription_identifier.py` - Tests subscription detection functionality

## CI/CD

These tests are automatically run in GitHub Actions on every push and pull request.
