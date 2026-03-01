"""Integration checks for demo seed service.

Run with:
  cd backend && python tests/test_demo_seed_service.py
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import func

from app.database import Base, SessionLocal, engine
from app.models import Account, Category, Transaction, User
from app.services.demo_seed_service import DemoSeedService


def ensure_test_user(db) -> User:
    user_id = "demo-seed-test-user"
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        return user

    user = User(
        id=user_id,
        email="demo-seed-test@example.com",
        name="Demo Seed Test",
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def run_checks() -> bool:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = ensure_test_user(db)
        service = DemoSeedService(db, random_seed=123)
        summary = service.seed_for_user(
            user=user,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            reset=True,
        )

        assert summary["accounts_created"] >= 3, "Expected at least 3 accounts"

        accounts = db.query(Account).filter(Account.user_id == user.id, Account.is_active == True).all()
        assert len(accounts) >= 3, "Seeded account count mismatch"
        assert any((account.currency or "").upper() != "EUR" for account in accounts), "Expected non-EUR account"

        categories = db.query(Category).filter(Category.user_id == user.id).all()
        with_instructions = [c for c in categories if c.categorization_instructions and c.categorization_instructions.strip()]
        assert len(with_instructions) >= 10, "Expected categorization instructions on major categories"

        txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
        assert txs, "Expected transactions to be generated"

        min_booked = min(tx.booked_at.date() for tx in txs)
        max_booked = max(tx.booked_at.date() for tx in txs)
        assert min_booked >= date(2025, 1, 1), "Transactions before start date"
        assert max_booked <= date(2025, 1, 31), "Transactions after end date"

        # Monthly financial constraints:
        # - income must exceed spending with at least 35% savings rate
        # - Housing should be the biggest monthly expense category
        category_by_id = {str(c.id): c for c in categories}
        income_total = Decimal("0")
        expense_total = Decimal("0")
        expense_by_category = {}

        for tx in txs:
            effective_cat_id = tx.category_id or tx.category_system_id
            category = category_by_id.get(str(effective_cat_id)) if effective_cat_id else None
            category_type = category.category_type if category else None

            if tx.amount > 0:
                if category_type != "transfer":
                    income_total += Decimal(str(tx.amount))
            elif tx.amount < 0:
                if category_type != "transfer":
                    spend = abs(Decimal(str(tx.amount)))
                    expense_total += spend
                    if category and category.category_type == "expense":
                        expense_by_category[category.name] = expense_by_category.get(category.name, Decimal("0")) + spend

        assert income_total > expense_total, "Expected income to be greater than spending"
        assert expense_total <= (income_total * Decimal("0.65")), (
            f"Expected >=35% savings rate. income={income_total}, expense={expense_total}"
        )

        housing_spend = expense_by_category.get("Housing", Decimal("0"))
        max_other = max(
            (amount for name, amount in expense_by_category.items() if name != "Housing"),
            default=Decimal("0"),
        )
        assert housing_spend > max_other, (
            f"Expected Housing to be largest monthly expense. housing={housing_spend}, max_other={max_other}"
        )

        # Seed-time balance integrity.
        for account in accounts:
            db.refresh(account)
            tx_sum = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user.id,
                Transaction.account_id == account.id,
            ).scalar()
            tx_sum = Decimal(str(tx_sum or 0))
            starting = Decimal(str(account.starting_balance or 0))
            computed = tx_sum + starting
            target = Decimal(str(account.balance_available or 0))
            assert account.starting_balance is not None, f"Missing starting balance on {account.name}"
            assert abs(computed - target) <= Decimal("0.01"), (
                f"Balance mismatch for {account.name}: computed={computed}, target={target}"
            )

        # Daily engine should be idempotent for a given day.
        append_summary = service.append_previous_day_transactions(
            user=user,
            target_date=date(2025, 2, 1),
        )
        assert not append_summary.get("skipped"), "Expected first daily append to create transactions"
        assert append_summary.get("transactions_created", 0) > 0, "Expected created daily transactions"

        appended_rows = db.query(Transaction).filter(
            Transaction.user_id == user.id,
            Transaction.external_id.ilike("demo-day-20250201-%"),
        ).all()
        assert appended_rows, "Expected rows with daily external-id prefix"
        assert max(tx.booked_at.date() for tx in appended_rows) <= date(2025, 2, 1), (
            "Daily append should not create future-dated transactions"
        )

        append_summary_2 = service.append_previous_day_transactions(
            user=user,
            target_date=date(2025, 2, 1),
        )
        assert append_summary_2.get("skipped"), "Expected second daily append to skip duplicate day"

        # If a day is already populated by the main seed, daily engine should skip.
        existing_day_skip = service.append_previous_day_transactions(
            user=user,
            target_date=date(2025, 1, 10),
        )
        assert existing_day_skip.get("skipped"), "Expected populated seeded day to be skipped"

        # Gap backfill should detect and fill missing calendar days.
        deleted_for_gap = db.query(Transaction).filter(
            Transaction.user_id == user.id,
            func.date(Transaction.booked_at) == date(2025, 1, 20),
        ).delete(synchronize_session=False)
        db.commit()
        assert deleted_for_gap > 0, "Expected at least one row deleted for gap test"

        coverage = service.ensure_demo_coverage(
            user=user,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert coverage.get("action") in {"filled_missing_days", "none"}, (
            f"Unexpected coverage action: {coverage}"
        )
        restored_for_gap = db.query(func.count(Transaction.id)).filter(
            Transaction.user_id == user.id,
            func.date(Transaction.booked_at) == date(2025, 1, 20),
        ).scalar() or 0
        assert restored_for_gap > 0, "Expected gap day to be restored"

        # Partial-month seed must never spill beyond requested end_date.
        service.seed_for_user(
            user=user,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 1),
            reset=True,
        )
        partial_txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
        assert partial_txs, "Expected at least one transaction for partial seed range"
        assert max(tx.booked_at.date() for tx in partial_txs) <= date(2025, 1, 1), (
            "Partial-month seed generated transactions beyond end_date"
        )

        print("Demo seed service checks passed")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"Demo seed service checks failed: {exc}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    ok = run_checks()
    sys.exit(0 if ok else 1)
