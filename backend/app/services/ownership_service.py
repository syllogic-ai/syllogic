"""
Ownership resolution and share-weighted attribution.

Public API:
- resolve_shares(owners) -> dict[person_id -> share]
- attribute_amount(amount, owners, person_id_or_none) -> float
- entity_ids_for_people(db, entity, person_ids) -> list[UUID]
- get_owners(db, entity, entity_id) -> list[dict]
"""
from __future__ import annotations

from typing import Iterable, Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Account, AccountOwner, Property, PropertyOwner, Vehicle, VehicleOwner

EntityType = Literal["account", "property", "vehicle"]

_ASSOC = {
    "account": (AccountOwner, "account_id"),
    "property": (PropertyOwner, "property_id"),
    "vehicle": (VehicleOwner, "vehicle_id"),
}


def resolve_shares(owners: list[dict]) -> dict[str, float]:
    if not owners:
        return {}
    none_count = sum(1 for o in owners if o.get("share") is None)
    if none_count == len(owners):
        equal = 1.0 / len(owners)
        return {str(o["person_id"]): equal for o in owners}
    if none_count > 0:
        raise ValueError(
            "ownership shares must be all NULL (equal split) or all explicit; "
            f"got {none_count} NULL of {len(owners)}"
        )
    return {str(o["person_id"]): float(o["share"]) for o in owners}


def attribute_amount(amount: float, owners: list[dict], person_id: str | None) -> float:
    if person_id is None:
        return amount
    return amount * resolve_shares(owners).get(str(person_id), 0.0)


def get_owners(db: Session, entity: EntityType, entity_id: UUID | str) -> list[dict]:
    Assoc, fk = _ASSOC[entity]
    rows = db.query(Assoc).filter(getattr(Assoc, fk) == entity_id).all()
    return [
        {"person_id": str(r.person_id), "share": float(r.share) if r.share is not None else None}
        for r in rows
    ]


def entity_ids_for_people(
    db: Session, entity: EntityType, person_ids: Iterable[UUID | str]
) -> list[UUID]:
    pids = list(person_ids)
    if not pids:
        return []
    Assoc, fk = _ASSOC[entity]
    rows = db.query(getattr(Assoc, fk)).filter(Assoc.person_id.in_(pids)).distinct().all()
    return [r[0] for r in rows]
