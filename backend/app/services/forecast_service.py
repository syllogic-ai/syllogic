"""Deterministic cash-flow / balance projection engine.

Pure functions only — no DB access here, mirroring pnl_service.py's split
(callers gather data from SQLAlchemy, this module just does math). A cash
forecast combines two legs:

  1. "known" — active RecurringTransaction rows, walked forward via
     compute_next_due_date(). Direction comes from `RecurringDefinition.is_income`
     (set by the caller from Category.category_type — see routes/forecast.py):
     income rows add to the balance, everything else (expense/transfer/no
     category) subtracts, matching what tasks/recurring_transaction_tasks.py
     actually materializes.
  2. "variable" — everything else, projected forward as a flat trailing
     daily average (see routes/forecast.py for how that average, and its
     stddev, are computed — excluding transactions already linked to a
     recurring definition, to avoid double-counting them).

Both legs are summed into a daily cumulative balance series starting from
the current summed account balance. A confidence band around that mid line
is derived from the trailing daily net's stddev under a random-walk
assumption (daily nets i.i.d.): band width at day t is `z * stddev *
sqrt(t)`. The recurring leg is deterministic and shifts low/mid/high
equally — it contributes no variance. No trend/seasonality modeling.

Investment/savings (growth) accounts are projected separately by
`project_compounding_balance`, using a flat historical daily rate derived
from AccountBalance history rather than transactions, since their balance
moves mainly via price change, not postings. The route sums both legs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from app.services.recurring_transaction_schedule_service import compute_next_due_date

_BAND_Z = Decimal("1")  # ~68% band width, one trailing-net stddev


@dataclass(frozen=True)
class RecurringDefinition:
    frequency: str
    amount: Decimal  # positive magnitude, as stored on RecurringTransaction
    next_due_date: date
    end_date: Optional[date] = None
    is_income: bool = False


@dataclass(frozen=True)
class ForecastPoint:
    day: date
    projected_balance: Decimal
    low: Decimal
    high: Decimal


@dataclass(frozen=True)
class ForecastResult:
    series: list[ForecastPoint]
    starting_balance: Decimal
    projected_balance_at_horizon: Decimal
    projected_balance_low_at_horizon: Decimal
    projected_balance_high_at_horizon: Decimal
    projected_net_cash_flow: Decimal
    projected_income: Decimal
    projected_expenses: Decimal


@dataclass(frozen=True)
class CompoundingPoint:
    day: date
    balance: Decimal


@dataclass(frozen=True)
class CompoundingResult:
    series: list[CompoundingPoint]
    starting_balance: Decimal
    balance_at_horizon: Decimal


def _recurring_occurrences(
    recurring: list[RecurringDefinition], start: date, end: date
) -> dict[date, Decimal]:
    """Map day -> signed amount contributed by recurring definitions landing in [start, end]."""
    occurrences: dict[date, Decimal] = {}
    for r in recurring:
        due = r.next_due_date
        # next_due_date can be in the past if the daily beat tick hasn't
        # materialized it yet — walk forward to the first occurrence in range.
        while due < start:
            due = compute_next_due_date(r.frequency, due)
        while due <= end:
            if r.end_date and due > r.end_date:
                break
            signed = abs(r.amount) if r.is_income else -abs(r.amount)
            occurrences[due] = occurrences.get(due, Decimal("0")) + signed
            due = compute_next_due_date(r.frequency, due)
    return occurrences


def project_cash_flow(
    *,
    starting_balance: Decimal,
    recurring: list[RecurringDefinition],
    trailing_daily_net: Decimal,
    trailing_daily_stddev: Decimal = Decimal("0"),
    horizon_days: int,
    as_of: Optional[date] = None,
) -> ForecastResult:
    """Project daily balance forward `horizon_days` days from `as_of` (default today).

    `trailing_daily_net` is the average daily net (income - expenses) from
    non-recurring-linked transactions over some trailing history window,
    computed by the caller and passed in as a single number so this
    function stays DB-free and easy to unit test. `trailing_daily_stddev`
    is the population stddev of that same daily-net series, used to widen
    the low/high band as the horizon grows (see module docstring).
    """
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")

    start = as_of or date.today()
    end = start + timedelta(days=horizon_days)
    recurring_by_day = _recurring_occurrences(recurring, start + timedelta(days=1), end)

    series: list[ForecastPoint] = [
        ForecastPoint(
            day=start,
            projected_balance=starting_balance,
            low=starting_balance,
            high=starting_balance,
        )
    ]
    balance = starting_balance
    projected_income = Decimal("0")
    projected_expenses = Decimal("0")

    day = start
    t = 0
    while day < end:
        day = day + timedelta(days=1)
        t += 1
        day_net = trailing_daily_net + recurring_by_day.get(day, Decimal("0"))
        if day_net > 0:
            projected_income += day_net
        else:
            projected_expenses += -day_net
        balance += day_net

        band = _BAND_Z * trailing_daily_stddev * Decimal(math.sqrt(t))
        series.append(
            ForecastPoint(
                day=day,
                projected_balance=balance,
                low=balance - band,
                high=balance + band,
            )
        )

    last = series[-1]
    return ForecastResult(
        series=series,
        starting_balance=starting_balance,
        projected_balance_at_horizon=balance,
        projected_balance_low_at_horizon=last.low,
        projected_balance_high_at_horizon=last.high,
        projected_net_cash_flow=balance - starting_balance,
        projected_income=projected_income,
        projected_expenses=projected_expenses,
    )


def project_compounding_balance(
    *,
    starting_balance: Decimal,
    daily_rate: Decimal,
    horizon_days: int,
    as_of: Optional[date] = None,
) -> CompoundingResult:
    """Project a balance forward under flat daily compounding.

    `daily_rate` is a flat per-day growth rate (e.g. derived from historical
    AccountBalance appreciation by the caller — see routes/forecast.py).
    Used for investment/crypto ("growth") accounts, whose balance moves
    mainly via price change rather than transactions, so the transaction-
    based flat-average leg in `project_cash_flow` doesn't apply to them.
    """
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")

    start = as_of or date.today()
    end = start + timedelta(days=horizon_days)

    series: list[CompoundingPoint] = [CompoundingPoint(day=start, balance=starting_balance)]
    balance = starting_balance
    day = start
    while day < end:
        day = day + timedelta(days=1)
        balance = balance * (1 + daily_rate)
        series.append(CompoundingPoint(day=day, balance=balance))

    return CompoundingResult(
        series=series, starting_balance=starting_balance, balance_at_horizon=balance
    )
