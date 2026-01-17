"""
Seed script to populate the database with dummy data.
Run with: python seed_data.py
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal, Base
from app.models import Account, Category, Transaction, User
from app.db_helpers import get_or_create_system_user

# Create tables
Base.metadata.create_all(bind=engine)


def create_accounts(db: Session, user_id: str) -> list[Account]:
    accounts = [
        Account(
            user_id=user_id,
            name="Main Checking",
            account_type="checking",
            institution="Revolut",
            currency="EUR",
            balance_current=Decimal("3245.67"),
        ),
        Account(
            user_id=user_id,
            name="Savings",
            account_type="savings",
            institution="Revolut",
            currency="EUR",
            balance_current=Decimal("15000.00"),
        ),
        Account(
            user_id=user_id,
            name="Credit Card",
            account_type="credit",
            institution="Visa",
            currency="EUR",
            balance_current=Decimal("-892.45"),
        ),
    ]

    for account in accounts:
        db.add(account)
    db.commit()

    for account in accounts:
        db.refresh(account)

    return accounts


def create_categories(db: Session, user_id: str) -> list[Category]:
    categories_data = [
        # Expenses
        {"name": "Groceries", "category_type": "expense", "color": "#10B981", "icon": "shopping-cart", "is_system": True},
        {"name": "Transport", "category_type": "expense", "color": "#3B82F6", "icon": "car", "is_system": True},
        {"name": "Utilities", "category_type": "expense", "color": "#F59E0B", "icon": "zap", "is_system": True},
        {"name": "Entertainment", "category_type": "expense", "color": "#8B5CF6", "icon": "tv", "is_system": True},
        {"name": "Dining Out", "category_type": "expense", "color": "#EC4899", "icon": "utensils", "is_system": True},
        {"name": "Shopping", "category_type": "expense", "color": "#F97316", "icon": "shopping-bag", "is_system": True},
        {"name": "Healthcare", "category_type": "expense", "color": "#EF4444", "icon": "heart", "is_system": True},
        {"name": "Subscriptions", "category_type": "expense", "color": "#6366F1", "icon": "credit-card", "is_system": True},
        {"name": "Education", "category_type": "expense", "color": "#14B8A6", "icon": "book", "is_system": True},
        {"name": "Housing", "category_type": "expense", "color": "#64748B", "icon": "home", "is_system": True},
        # Income
        {"name": "Salary", "category_type": "income", "color": "#22C55E", "icon": "briefcase", "is_system": True},
        {"name": "Freelance", "category_type": "income", "color": "#06B6D4", "icon": "laptop", "is_system": True},
        {"name": "Investment Income", "category_type": "income", "color": "#A855F7", "icon": "trending-up", "is_system": True},
        # Transfer
        {"name": "Transfer", "category_type": "transfer", "color": "#94A3B8", "icon": "repeat", "is_system": True},
    ]

    categories = []
    for cat_data in categories_data:
        cat_data["user_id"] = user_id
        category = Category(**cat_data)
        db.add(category)
        categories.append(category)

    db.commit()

    for category in categories:
        db.refresh(category)

    return categories


def create_transactions(db: Session, accounts: list[Account], categories: list[Category], user_id: str) -> None:
    # Get category references
    expense_categories = [c for c in categories if c.category_type == "expense"]
    income_categories = [c for c in categories if c.category_type == "income"]

    # Transaction templates
    expense_templates = [
        {"description": "LIDL", "merchant": "Lidl", "category": "Groceries", "amount_range": (15, 120)},
        {"description": "ALBERT HEIJN", "merchant": "Albert Heijn", "category": "Groceries", "amount_range": (20, 150)},
        {"description": "JUMBO SUPERMARKET", "merchant": "Jumbo", "category": "Groceries", "amount_range": (25, 100)},
        {"description": "NS STATION", "merchant": "NS", "category": "Transport", "amount_range": (5, 50)},
        {"description": "SHELL FUEL", "merchant": "Shell", "category": "Transport", "amount_range": (40, 100)},
        {"description": "UBER TRIP", "merchant": "Uber", "category": "Transport", "amount_range": (8, 35)},
        {"description": "VATTENFALL ENERGY", "merchant": "Vattenfall", "category": "Utilities", "amount_range": (80, 200)},
        {"description": "ZIGGO INTERNET", "merchant": "Ziggo", "category": "Utilities", "amount_range": (50, 70)},
        {"description": "NETFLIX", "merchant": "Netflix", "category": "Subscriptions", "amount_range": (12, 18)},
        {"description": "SPOTIFY", "merchant": "Spotify", "category": "Subscriptions", "amount_range": (10, 15)},
        {"description": "CINEMA PATHE", "merchant": "Pathe", "category": "Entertainment", "amount_range": (12, 30)},
        {"description": "RESTAURANT", "merchant": None, "category": "Dining Out", "amount_range": (20, 80)},
        {"description": "CAFE DE WERELD", "merchant": "Cafe de Wereld", "category": "Dining Out", "amount_range": (10, 40)},
        {"description": "MCDONALDS", "merchant": "McDonalds", "category": "Dining Out", "amount_range": (8, 20)},
        {"description": "AMAZON", "merchant": "Amazon", "category": "Shopping", "amount_range": (15, 200)},
        {"description": "ZALANDO", "merchant": "Zalando", "category": "Shopping", "amount_range": (30, 150)},
        {"description": "H&M", "merchant": "H&M", "category": "Shopping", "amount_range": (20, 100)},
        {"description": "APOTHEEK", "merchant": "Pharmacy", "category": "Healthcare", "amount_range": (5, 50)},
        {"description": "HUISARTS", "merchant": "Doctor", "category": "Healthcare", "amount_range": (20, 100)},
        {"description": "RENT PAYMENT", "merchant": "Landlord", "category": "Housing", "amount_range": (1200, 1200)},
    ]

    income_templates = [
        {"description": "SALARY PAYMENT", "merchant": "Employer", "category": "Salary", "amount_range": (3500, 4500)},
        {"description": "FREELANCE PROJECT", "merchant": "Client", "category": "Freelance", "amount_range": (500, 2000)},
        {"description": "DIVIDEND PAYMENT", "merchant": "Broker", "category": "Investment Income", "amount_range": (50, 200)},
    ]

    checking = accounts[0]
    savings = accounts[1]
    credit = accounts[2]

    now = datetime.now()
    transactions = []

    # Generate 3 months of transactions
    for days_ago in range(90):
        date = now - timedelta(days=days_ago)

        # 2-5 expense transactions per day on weekdays, 3-7 on weekends
        is_weekend = date.weekday() >= 5
        num_expenses = random.randint(3, 7) if is_weekend else random.randint(2, 5)

        for _ in range(num_expenses):
            template = random.choice(expense_templates)
            amount = -round(random.uniform(*template["amount_range"]), 2)

            # Find category
            category = next((c for c in expense_categories if c.name == template["category"]), None)

            # 80% of transactions are categorized
            if random.random() > 0.8:
                category = None

            # 70% from checking, 30% from credit
            account = checking if random.random() > 0.3 else credit

            category_id_value = category.id if category else None
            transaction = Transaction(
                user_id=user_id,
                account_id=account.id,
                transaction_type="debit",
                amount=Decimal(str(amount)),
                currency="EUR",
                description=template["description"],
                merchant=template["merchant"],
                category_id=category_id_value,  # Set category_id equal to category_system_id
                category_system_id=category_id_value,  # Use category_system_id for AI-assigned
                booked_at=date.replace(
                    hour=random.randint(8, 22),
                    minute=random.randint(0, 59),
                ),
            )
            transactions.append(transaction)

    # Monthly salary (on the 25th of each month)
    for month_offset in range(3):
        salary_date = (now - timedelta(days=30 * month_offset)).replace(day=25)
        if salary_date <= now:
            salary_cat = next((c for c in income_categories if c.name == "Salary"), None)
            salary_category_id = salary_cat.id if salary_cat else None
            transactions.append(
                Transaction(
                    user_id=user_id,
                    account_id=checking.id,
                    transaction_type="credit",
                    amount=Decimal(str(round(random.uniform(3500, 4500), 2))),
                    currency="EUR",
                    description="SALARY PAYMENT - EMPLOYER BV",
                    merchant="Employer BV",
                    category_id=salary_category_id,  # Set category_id equal to category_system_id
                    category_system_id=salary_category_id,
                    booked_at=salary_date.replace(hour=9, minute=0),
                )
            )

    # Some freelance income
    for _ in range(5):
        days_ago = random.randint(0, 90)
        date = now - timedelta(days=days_ago)
        freelance_cat = next((c for c in income_categories if c.name == "Freelance"), None)
        freelance_category_id = freelance_cat.id if freelance_cat else None
        transactions.append(
            Transaction(
                user_id=user_id,
                account_id=checking.id,
                transaction_type="credit",
                amount=Decimal(str(round(random.uniform(500, 2000), 2))),
                currency="EUR",
                description="FREELANCE PROJECT PAYMENT",
                merchant="Various Client",
                category_id=freelance_category_id,  # Set category_id equal to category_system_id
                category_system_id=freelance_category_id,
                booked_at=date.replace(
                    hour=random.randint(9, 17),
                    minute=random.randint(0, 59),
                ),
            )
        )

    # Add all transactions
    for txn in transactions:
        db.add(txn)

    db.commit()
    print(f"Created {len(transactions)} transactions")


def clear_data(db: Session, user_id: str) -> None:
    db.query(Transaction).filter(Transaction.user_id == user_id).delete()
    db.query(Category).filter(Category.user_id == user_id).delete()
    db.query(Account).filter(Account.user_id == user_id).delete()
    db.commit()


def seed():
    db = SessionLocal()
    try:
        # Get or create system user
        print("Setting up system user...")
        user = get_or_create_system_user(db)
        user_id = user.id
        print(f"Using user_id: {user_id}")

        print("Clearing existing data...")
        clear_data(db, user_id)

        print("Creating accounts...")
        accounts = create_accounts(db, user_id)
        print(f"Created {len(accounts)} accounts")

        print("Creating categories...")
        categories = create_categories(db, user_id)
        print(f"Created {len(categories)} categories")

        print("Creating transactions...")
        create_transactions(db, accounts, categories, user_id)

        print("\nSeeding complete!")
        print(f"Total accounts: {db.query(Account).filter(Account.user_id == user_id).count()}")
        print(f"Total categories: {db.query(Category).filter(Category.user_id == user_id).count()}")
        print(f"Total transactions: {db.query(Transaction).filter(Transaction.user_id == user_id).count()}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
