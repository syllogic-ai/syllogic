from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case
from typing import Optional
from datetime import datetime
from uuid import UUID

from app.database import get_db
from app.models import Transaction, Category, Account
from app.db_helpers import get_user_id

router = APIRouter()


@router.get("/cashflow/monthly")
def get_monthly_cashflow(
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    category_id: Optional[UUID] = None,
    account_id: Optional[UUID] = None,
    uncategorized: Optional[bool] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get monthly income and expenses for bar chart"""
    user_id = get_user_id(user_id)
    query = db.query(
        extract("year", Transaction.booked_at).label("year"),
        extract("month", Transaction.booked_at).label("month"),
        func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)).label("income"),
        func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)).label("expenses"),
    ).filter(Transaction.user_id == user_id)

    if from_date:
        query = query.filter(Transaction.booked_at >= from_date)
    if to_date:
        query = query.filter(Transaction.booked_at <= to_date)
    if category_id:
        # Check both category_id and category_system_id
        query = query.filter(
            (Transaction.category_id == category_id) |
            (Transaction.category_system_id == category_id)
        )
    if uncategorized:
        query = query.filter(
            Transaction.category_id.is_(None),
            Transaction.category_system_id.is_(None)
        )
    if account_id:
        query = query.filter(Transaction.account_id == account_id)

    results = (
        query.group_by(
            extract("year", Transaction.booked_at),
            extract("month", Transaction.booked_at),
        )
        .order_by(
            extract("year", Transaction.booked_at),
            extract("month", Transaction.booked_at),
        )
        .all()
    )

    return [
        {
            "month": f"{int(r.year)}-{int(r.month):02d}",
            "income": float(r.income) if r.income else 0,
            "expenses": float(r.expenses) if r.expenses else 0,
        }
        for r in results
    ]


@router.get("/sankey")
def get_sankey_data(
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    account_id: Optional[UUID] = None,
    uncategorized: Optional[bool] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get data for Sankey diagram: income -> expense categories"""
    user_id = get_user_id(user_id)

    # Get total income
    income_query = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.amount > 0
    )
    if from_date:
        income_query = income_query.filter(Transaction.booked_at >= from_date)
    if to_date:
        income_query = income_query.filter(Transaction.booked_at <= to_date)
    if account_id:
        income_query = income_query.filter(Transaction.account_id == account_id)

    total_income = income_query.scalar() or 0

    # Get income by category
    income_by_cat_query = db.query(
        Category.name.label("category_name"),
        func.sum(Transaction.amount).label("total"),
    ).outerjoin(
        Category,
        (Transaction.category_id == Category.id) | (Transaction.category_system_id == Category.id)
    ).filter(
        Transaction.user_id == user_id,
        Transaction.amount > 0
    )

    if from_date:
        income_by_cat_query = income_by_cat_query.filter(Transaction.booked_at >= from_date)
    if to_date:
        income_by_cat_query = income_by_cat_query.filter(Transaction.booked_at <= to_date)
    if account_id:
        income_by_cat_query = income_by_cat_query.filter(Transaction.account_id == account_id)
    if uncategorized:
        income_by_cat_query = income_by_cat_query.filter(
            Transaction.category_id.is_(None),
            Transaction.category_system_id.is_(None)
        )

    income_by_cat = income_by_cat_query.group_by(Category.name).all()

    # Get expenses by category
    expense_query = db.query(
        Category.name.label("category_name"),
        func.sum(func.abs(Transaction.amount)).label("total"),
    ).outerjoin(
        Category,
        (Transaction.category_id == Category.id) | (Transaction.category_system_id == Category.id)
    ).filter(
        Transaction.user_id == user_id,
        Transaction.amount < 0
    )

    if from_date:
        expense_query = expense_query.filter(Transaction.booked_at >= from_date)
    if to_date:
        expense_query = expense_query.filter(Transaction.booked_at <= to_date)
    if account_id:
        expense_query = expense_query.filter(Transaction.account_id == account_id)
    if uncategorized:
        expense_query = expense_query.filter(
            Transaction.category_id.is_(None),
            Transaction.category_system_id.is_(None)
        )

    expenses_by_category = expense_query.group_by(Category.name).all()

    # Build nodes and links for Sankey
    nodes = []
    links = []
    node_index = {}

    # Add income source nodes
    for item in income_by_cat:
        name = item.category_name or "Other Income"
        source_name = f"Income: {name}"
        if source_name not in node_index:
            node_index[source_name] = len(nodes)
            nodes.append({"name": source_name})

    # Add central "Total Income" node
    node_index["Total Income"] = len(nodes)
    nodes.append({"name": "Total Income"})

    # Add expense category nodes
    for item in expenses_by_category:
        name = item.category_name or "Uncategorized"
        if name not in node_index:
            node_index[name] = len(nodes)
            nodes.append({"name": name})

    # Add savings node for leftover
    total_expenses = sum(item.total for item in expenses_by_category)
    savings = float(total_income) - float(total_expenses)
    if savings > 0:
        node_index["Savings"] = len(nodes)
        nodes.append({"name": "Savings"})

    # Create links from income sources to Total Income
    for item in income_by_cat:
        name = item.category_name or "Other Income"
        source_name = f"Income: {name}"
        links.append({
            "source": node_index[source_name],
            "target": node_index["Total Income"],
            "value": float(item.total),
        })

    # Create links from Total Income to expense categories
    for item in expenses_by_category:
        name = item.category_name or "Uncategorized"
        links.append({
            "source": node_index["Total Income"],
            "target": node_index[name],
            "value": float(item.total),
        })

    # Add savings link if positive
    if savings > 0:
        links.append({
            "source": node_index["Total Income"],
            "target": node_index["Savings"],
            "value": savings,
        })

    return {
        "nodes": nodes,
        "links": links,
        "totalIncome": float(total_income),
        "totalExpenses": float(total_expenses),
        "savings": savings,
    }


@router.get("/account-balances")
def get_account_balances(
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    category_id: Optional[UUID] = None,
    account_id: Optional[UUID] = None,
    uncategorized: Optional[bool] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Get account balances based on filters.
    For date range: calculates balance at end of period (sum of transactions up to end_date).
    For category: only includes accounts that had transactions in those categories.
    """
    user_id = get_user_id(user_id)
    # Base query for accounts
    accounts_query = db.query(Account).filter(
        Account.user_id == user_id,
        Account.is_active == True
    )
    
    # If account_id filter is provided, only show that account
    if account_id:
        accounts_query = accounts_query.filter(Account.id == account_id)
    
    accounts = accounts_query.all()
    
    result = []
    
    for account in accounts:
        # If category filter is provided, check if this account has transactions in that category
        if category_id:
            has_transactions = db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
                (
                    (Transaction.category_id == category_id) |
                    (Transaction.category_system_id == category_id)
                )
            ).first()
            if not has_transactions:
                continue
        elif uncategorized:
            has_transactions = db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
                Transaction.category_id.is_(None),
                Transaction.category_system_id.is_(None)
            ).first()
            if not has_transactions:
                continue
        
        # Calculate balance based on date filters
        if to_date:
            # Calculate balance at end of period
            # Balance at to_date = current_balance - sum(transactions after to_date)
            transactions_after = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
                Transaction.booked_at > to_date
            ).scalar() or 0
            
            # If category filter, only consider transactions in that category
            if category_id:
                transactions_after = db.query(func.sum(Transaction.amount)).filter(
                    Transaction.user_id == user_id,
                    Transaction.account_id == account.id,
                    Transaction.booked_at > to_date,
                    (
                        (Transaction.category_id == category_id) |
                        (Transaction.category_system_id == category_id)
                    )
                ).scalar() or 0
                # For category filter, calculate net change in period
                transactions_in_period = db.query(func.sum(Transaction.amount)).filter(
                    Transaction.user_id == user_id,
                    Transaction.account_id == account.id,
                    Transaction.booked_at >= (from_date or datetime.min),
                    Transaction.booked_at <= to_date,
                    (
                        (Transaction.category_id == category_id) |
                        (Transaction.category_system_id == category_id)
                    )
                ).scalar() or 0
                balance = float(transactions_in_period)
            elif uncategorized:
                transactions_after = db.query(func.sum(Transaction.amount)).filter(
                    Transaction.user_id == user_id,
                    Transaction.account_id == account.id,
                    Transaction.booked_at > to_date,
                    Transaction.category_id.is_(None),
                    Transaction.category_system_id.is_(None)
                ).scalar() or 0
                # For uncategorized filter, calculate net change in period
                transactions_in_period = db.query(func.sum(Transaction.amount)).filter(
                    Transaction.user_id == user_id,
                    Transaction.account_id == account.id,
                    Transaction.booked_at >= (from_date or datetime.min),
                    Transaction.booked_at <= to_date,
                    Transaction.category_id.is_(None),
                    Transaction.category_system_id.is_(None)
                ).scalar() or 0
                balance = float(transactions_in_period)
            else:
                # Use functional_balance instead of balance_current
                balance = float(account.functional_balance) if account.functional_balance else 0.0
                balance = balance - float(transactions_after)
        elif from_date:
            # Calculate balance change during period (from from_date to now)
            balance_query = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
                Transaction.booked_at >= from_date
            )
            if category_id:
                balance_query = balance_query.filter(
                    (Transaction.category_id == category_id) |
                    (Transaction.category_system_id == category_id)
                )
            elif uncategorized:
                balance_query = balance_query.filter(
                    Transaction.category_id.is_(None),
                    Transaction.category_system_id.is_(None)
                )
            balance_change = balance_query.scalar() or 0
            if category_id or uncategorized:
                balance = float(balance_change)
            else:
                balance = float(account.functional_balance) if account.functional_balance else 0.0
        elif category_id:
            # Category filter only: show net change for transactions in that category
            balance = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
                (
                    (Transaction.category_id == category_id) |
                    (Transaction.category_system_id == category_id)
                )
            ).scalar() or 0
            balance = float(balance)
        elif uncategorized:
            # Uncategorized filter only: show net change for uncategorized transactions
            balance = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
                Transaction.category_id.is_(None),
                Transaction.category_system_id.is_(None)
            ).scalar() or 0
            balance = float(balance)
        else:
            # No date or category filters, use current balance
            balance = float(account.balance_current)
        
        result.append({
            "account_id": str(account.id),
            "name": account.name,
            "balance": balance,
            "currency": account.currency,
            "account_type": account.account_type,
        })
    
    return result
