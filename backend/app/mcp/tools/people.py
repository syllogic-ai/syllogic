"""
People and household tools for the MCP server.
"""
from __future__ import annotations

from app.mcp.dependencies import get_db
from app.models import Account, Person, Property, Vehicle
from app.services.ownership_service import attribute_amount, get_owners
from app.mcp.tools.investments import INVESTMENT_ACCOUNT_TYPES


def list_people(user_id: str) -> list[dict]:
    """
    List all people in the user's household.

    Args:
        user_id: The user's ID

    Returns:
        List of person dicts with id, name, kind, color.
    """
    with get_db() as db:
        rows = (
            db.query(Person)
            .filter(Person.user_id == user_id)
            .order_by(Person.kind, Person.created_at)
            .all()
        )
        return [
            {"id": str(p.id), "name": p.name, "kind": p.kind, "color": p.color}
            for p in rows
        ]


def get_household_summary(
    user_id: str, person_ids: list[str] | None = None
) -> dict:
    """
    Per-person net worth breakdown across cash, investments, properties, vehicles.

    If ``person_ids`` is None, returns one entry per person in the household.
    Otherwise returns entries only for the specified people.

    Args:
        user_id: The user's ID
        person_ids: Optional list of person UUIDs to filter results

    Returns:
        Dict with a ``people`` list; each entry has person_id, name, cash,
        investments, properties, vehicles, total.
    """
    with get_db() as db:
        people = db.query(Person).filter(Person.user_id == user_id).all()
        if person_ids is not None:
            pid_set = set(person_ids)
            people = [p for p in people if str(p.id) in pid_set]

        accounts = (
            db.query(Account)
            .filter(Account.user_id == user_id, Account.is_active.is_(True))
            .all()
        )
        properties = (
            db.query(Property)
            .filter(Property.user_id == user_id, Property.is_active.is_(True))
            .all()
        )
        vehicles = (
            db.query(Vehicle)
            .filter(Vehicle.user_id == user_id, Vehicle.is_active.is_(True))
            .all()
        )

        # Cache owners per entity to avoid N*M queries.
        account_owners = {str(a.id): get_owners(db, "account", a.id) for a in accounts}
        property_owners = {str(p.id): get_owners(db, "property", p.id) for p in properties}
        vehicle_owners = {str(v.id): get_owners(db, "vehicle", v.id) for v in vehicles}

        out: list[dict] = []
        for person in people:
            pid = str(person.id)
            cash = 0.0
            investments = 0.0
            properties_total = 0.0
            vehicles_total = 0.0

            for a in accounts:
                owners = account_owners[str(a.id)]
                if pid not in {o["person_id"] for o in owners}:
                    continue
                balance = float(a.functional_balance or 0)
                amt = attribute_amount(balance, owners, pid)
                if (a.account_type or "") in INVESTMENT_ACCOUNT_TYPES:
                    investments += amt
                else:
                    cash += amt

            for pr in properties:
                owners = property_owners[str(pr.id)]
                if pid not in {o["person_id"] for o in owners}:
                    continue
                properties_total += attribute_amount(float(pr.current_value or 0), owners, pid)

            for v in vehicles:
                owners = vehicle_owners[str(v.id)]
                if pid not in {o["person_id"] for o in owners}:
                    continue
                vehicles_total += attribute_amount(float(v.current_value or 0), owners, pid)

            out.append({
                "person_id": pid,
                "name": person.name,
                "cash": round(cash, 2),
                "investments": round(investments, 2),
                "properties": round(properties_total, 2),
                "vehicles": round(vehicles_total, 2),
                "total": round(cash + investments + properties_total + vehicles_total, 2),
            })
        return {"people": out}
