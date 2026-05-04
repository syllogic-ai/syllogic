"""Routine output and request payload schemas."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class EvidenceItem(BaseModel):
    source: str
    url: str
    quote: str
    relevance: str


class HouseholdPerson(BaseModel):
    person_id: str = Field(alias="personId")
    name: str
    cash: float
    investments: float
    properties: float
    vehicles: float
    total: float

    class Config:
        populate_by_name = True


class HouseholdSection(BaseModel):
    people: list[HouseholdPerson]


class PositionRow(BaseModel):
    label: str
    current: float
    target: Optional[float] = None
    delta_pct: Optional[float] = Field(default=None, alias="deltaPct")
    note: Optional[str] = None

    class Config:
        populate_by_name = True


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    date_iso: str = Field(alias="dateIso")
    summary: str

    class Config:
        populate_by_name = True


class Recommendation(BaseModel):
    severity: Literal["info", "monitor", "act_now"]
    title: str
    rationale: str
    proposed_change: Optional[str] = Field(default=None, alias="proposedChange")

    class Config:
        populate_by_name = True


class RoutineOutput(BaseModel):
    status: Literal["GREEN", "AMBER", "RED"]
    confidence: Literal["low", "medium", "high"]
    headline: str
    summary: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    household: HouseholdSection
    positions: list[PositionRow] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    flags: dict[str, bool] = Field(default_factory=dict)


class ParseScheduleRequest(BaseModel):
    text: str


class ParseScheduleResponse(BaseModel):
    cron: str
    timezone: str
    human_readable: str = Field(alias="humanReadable")

    class Config:
        populate_by_name = True


SLOT_TOLERANCE = 0.01


def validate_slots(slots: list[dict], total_monthly: float) -> None:
    if not slots:
        raise ValueError("at least one slot is required")

    ids: set[str] = set()
    for s in slots:
        sid = s.get("id")
        if not sid:
            raise ValueError("slot id is required")
        if sid in ids:
            raise ValueError(f"duplicate slot id: {sid}")
        ids.add(sid)
        amount = float(s.get("amount", 0))
        if amount <= 0:
            raise ValueError(f"amount must be > 0; got {amount}")
        kind = s.get("kind")
        if kind == "pinned":
            if not (s.get("symbol") or "").strip():
                raise ValueError("pinned slot requires symbol")
        elif kind == "discretionary":
            if not (s.get("theme") or "").strip():
                raise ValueError("discretionary slot requires theme")
        else:
            raise ValueError(f"unknown slot kind: {kind}")

    total = sum(float(s["amount"]) for s in slots)
    if abs(total - float(total_monthly)) > SLOT_TOLERANCE:
        raise ValueError(f"slot sum ({total:.2f}) must equal totalMonthly ({float(total_monthly):.2f})")


class CashSnapshotItem(BaseModel):
    account_id: str = Field(alias="accountId")
    account_name: str = Field(alias="accountName")
    idle_cash: float = Field(alias="idleCash")
    currency: str

    class Config:
        populate_by_name = True


class RecentActivityItem(BaseModel):
    symbol: str
    net_bought: float = Field(alias="netBought")
    trade_count: int = Field(alias="tradeCount")
    as_of: str = Field(alias="asOf")

    class Config:
        populate_by_name = True


class PinnedResult(BaseModel):
    slot_id: str = Field(alias="slotId")
    symbol: str
    allocated_amount: float = Field(alias="allocatedAmount")
    verdict: Literal["keep", "reduce", "replace", "monitor"]
    rationale: str
    risk_flags: list[str] = Field(default_factory=list, alias="riskFlags")
    news_refs: list[int] = Field(default_factory=list, alias="newsRefs")
    proposed_replacement: Optional[dict] = Field(default=None, alias="proposedReplacement")

    class Config:
        populate_by_name = True


class TopPick(BaseModel):
    rank: int
    symbol: str
    name: str
    suggested_amount: float = Field(alias="suggestedAmount")
    rationale: str
    risk_flags: list[str] = Field(default_factory=list, alias="riskFlags")
    news_refs: list[int] = Field(default_factory=list, alias="newsRefs")

    class Config:
        populate_by_name = True


class DiscretionaryResult(BaseModel):
    slot_id: str = Field(alias="slotId")
    theme: str
    allocated_amount: float = Field(alias="allocatedAmount")
    top_picks: list[TopPick] = Field(default_factory=list, alias="topPicks")

    class Config:
        populate_by_name = True


class ProposedBuy(BaseModel):
    symbol: str
    amount: float
    source: Literal["pinned", "discretionary"]
    slot_id: str = Field(alias="slotId")

    class Config:
        populate_by_name = True


class MonthlyAction(BaseModel):
    proposed_buys: list[ProposedBuy] = Field(default_factory=list, alias="proposedBuys")
    idle_cash_nudge: Optional[str] = Field(default=None, alias="idleCashNudge")
    notes: list[str] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class InvestmentPlanOutput(BaseModel):
    total_monthly: float = Field(alias="totalMonthly")
    currency: str
    cash_snapshot: list[CashSnapshotItem] = Field(default_factory=list, alias="cashSnapshot")
    recent_activity: list[RecentActivityItem] = Field(default_factory=list, alias="recentActivity")
    pinned: list[PinnedResult] = Field(default_factory=list)
    discretionary: list[DiscretionaryResult] = Field(default_factory=list)
    monthly_action: MonthlyAction = Field(alias="monthlyAction")
    evidence: list[EvidenceItem] = Field(default_factory=list)
    flags: dict[str, bool] = Field(default_factory=dict)

    class Config:
        populate_by_name = True
