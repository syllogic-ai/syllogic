"""
Smoke tests for list_people and get_household_summary MCP tools.

Exercises the person filter end-to-end:
  - list_accounts with person_ids excludes accounts not owned by the filter set
  - get_household_summary partitions a joint account's balance evenly across owners
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models import Account, AccountOwner, Person, User
from app.mcp.tools.accounts import list_accounts
from app.mcp.tools.people import get_household_summary, list_people


@pytest.fixture
def seeded_household(db_session):
    """
    Create one user, two people (self + partner), and three accounts:
      - self_only: owned by self, balance 100, type=checking
      - partner_only: owned by partner, balance 200, type=checking
      - joint: owned by both with NULL share (equal split), balance 1000, type=savings

    Yields (user_id, self_id, partner_id, {"self_only": uuid, "partner_only": uuid, "joint": uuid}).
    Cleans up on teardown.
    """
    user_id = str(uuid.uuid4())
    user = User(id=user_id, email=f"{user_id}@test.com")
    db_session.add(user)
    db_session.flush()

    self_person = Person(user_id=user_id, name="Me", kind="self", color="#FF0000")
    partner_person = Person(user_id=user_id, name="Partner", kind="member", color="#0000FF")
    db_session.add(self_person)
    db_session.add(partner_person)
    db_session.flush()

    self_id = str(self_person.id)
    partner_id = str(partner_person.id)

    # Create three accounts
    self_account = Account(
        user_id=user_id,
        name="Self Checking",
        account_type="checking",
        institution="TestBank",
        currency="EUR",
        provider="manual",
        is_active=True,
        starting_balance=Decimal("0"),
        functional_balance=Decimal("100"),
    )
    partner_account = Account(
        user_id=user_id,
        name="Partner Checking",
        account_type="checking",
        institution="TestBank",
        currency="EUR",
        provider="manual",
        is_active=True,
        starting_balance=Decimal("0"),
        functional_balance=Decimal("200"),
    )
    joint_account = Account(
        user_id=user_id,
        name="Joint Savings",
        account_type="savings",
        institution="TestBank",
        currency="EUR",
        provider="manual",
        is_active=True,
        starting_balance=Decimal("0"),
        functional_balance=Decimal("1000"),
    )
    for acct in (self_account, partner_account, joint_account):
        db_session.add(acct)
    db_session.flush()

    self_acct_id = str(self_account.id)
    partner_acct_id = str(partner_account.id)
    joint_acct_id = str(joint_account.id)

    # Ownership rows
    db_session.add(AccountOwner(account_id=self_account.id, person_id=self_person.id, share=None))
    db_session.add(AccountOwner(account_id=partner_account.id, person_id=partner_person.id, share=None))
    # Joint: both owners, no explicit share → equal split
    db_session.add(AccountOwner(account_id=joint_account.id, person_id=self_person.id, share=None))
    db_session.add(AccountOwner(account_id=joint_account.id, person_id=partner_person.id, share=None))

    db_session.commit()

    try:
        yield (
            user_id,
            self_id,
            partner_id,
            {
                "self_only": self_acct_id,
                "partner_only": partner_acct_id,
                "joint": joint_acct_id,
            },
        )
    finally:
        db_session.query(AccountOwner).filter(
            AccountOwner.account_id.in_([self_account.id, partner_account.id, joint_account.id])
        ).delete(synchronize_session=False)
        db_session.query(Account).filter(Account.user_id == user_id).delete(synchronize_session=False)
        db_session.query(Person).filter(Person.user_id == user_id).delete(synchronize_session=False)
        db_session.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db_session.commit()


def test_list_people_returns_both(seeded_household):
    user_id, self_id, partner_id, _ = seeded_household
    people = list_people(user_id=user_id)
    ids = {p["id"] for p in people}
    assert self_id in ids
    assert partner_id in ids
    assert len(people) == 2


def test_list_accounts_with_self_filter_excludes_partner_only(seeded_household):
    user_id, self_id, partner_id, accounts = seeded_household
    result = list_accounts(user_id=user_id, person_ids=[self_id])
    ids = {a["id"] for a in result}
    assert accounts["self_only"] in ids
    assert accounts["joint"] in ids
    assert accounts["partner_only"] not in ids


def test_household_summary_partitions_joint_account(seeded_household):
    user_id, self_id, partner_id, _ = seeded_household
    summary = get_household_summary(user_id=user_id)
    by_person = {p["person_id"]: p for p in summary["people"]}
    assert self_id in by_person
    assert partner_id in by_person
    # self: 100 (own) + 500 (half of 1000 joint) = 600
    assert by_person[self_id]["cash"] == pytest.approx(600.0)
    # partner: 200 (own) + 500 (half of 1000 joint) = 700
    assert by_person[partner_id]["cash"] == pytest.approx(700.0)


def test_household_summary_filter_by_person_ids(seeded_household):
    user_id, self_id, partner_id, _ = seeded_household
    summary = get_household_summary(user_id=user_id, person_ids=[self_id])
    assert len(summary["people"]) == 1
    assert summary["people"][0]["person_id"] == self_id
