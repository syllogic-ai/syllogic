"""
Pre-compute idle cash + recent trade activity to ground the investment-plan
agent before its loop starts.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.database import SessionLocal
from app.models import Account, BrokerTrade, Holding


def collect_grounding(user_id: str, days: int = 30) -> dict[str, list[dict]]:
    """
    Returns:
        {
            "cashSnapshot": [{ accountId, accountName, idleCash, currency }, ...],
            "recentActivity": [{ symbol, netBought, tradeCount, asOf }, ...]
        }

    Idle cash = balance_available − Σ(holding qty × avg_cost), clamped to 0.
    Recent activity sums signed quantity × price over `days`, grouped by symbol.
    """
    db = SessionLocal()
    try:
        accts = (
            db.query(Account)
            .filter(Account.user_id == user_id, Account.is_active.is_(True))
            .filter(Account.account_type.in_(("investment", "investment_brokerage", "investment_manual")))
            .all()
        )
        cash_snapshot: list[dict] = []
        for a in accts:
            balance = float(a.balance_available or a.functional_balance or 0)
            holdings = db.query(Holding).filter(Holding.account_id == a.id).all()
            held_value = 0.0
            for h in holdings:
                qty = float(h.quantity or 0)
                avg = float(h.avg_cost or 0)
                held_value += qty * avg
            idle = max(0.0, balance - held_value)
            cash_snapshot.append({
                "accountId": str(a.id),
                "accountName": a.name,
                "idleCash": round(idle, 2),
                "currency": a.currency or "EUR",
            })

        cutoff = (datetime.utcnow() - timedelta(days=days)).date()
        trades = (
            db.query(BrokerTrade)
            .join(Account, Account.id == BrokerTrade.account_id)
            .filter(Account.user_id == user_id, BrokerTrade.trade_date >= cutoff)
            .all()
        )
        per_symbol: dict[str, dict[str, Any]] = {}
        for t in trades:
            entry = per_symbol.setdefault(t.symbol, {"net": 0.0, "count": 0, "as_of": t.trade_date})
            sign = 1.0 if (t.side or "").lower() == "buy" else -1.0
            entry["net"] += sign * float(t.quantity or 0) * float(t.price or 0)
            entry["count"] += 1
            if t.trade_date > entry["as_of"]:
                entry["as_of"] = t.trade_date
        recent_activity = [
            {
                "symbol": sym,
                "netBought": round(v["net"], 2),
                "tradeCount": v["count"],
                "asOf": v["as_of"].isoformat(),
            }
            for sym, v in per_symbol.items()
        ]
        recent_activity.sort(key=lambda x: -abs(x["netBought"]))

        return {"cashSnapshot": cash_snapshot, "recentActivity": recent_activity}
    finally:
        db.close()
