"""Tests for `app.services.receipt_categorize` (Phase 5.2 of the
receipt-ingestion rework). See docs/specs/receipt-ingestion.md Part 5.2 and
docs/specs/receipt-ingestion-implementation.md 5.2 / "Phase 5 checkpoint":
a `category_id` outside the supplied set raises; a missing `line_id` raises;
a deposit inherits its parent's category even when the mocked model assigns
something else.

The LLM call is mocked throughout via `create_llm_clients`/`call_structured`
(patched on the `receipt_categorize` module, mirroring how
`test_receipt_extract.py` mocks stage 1) -- there is no API key available in
this environment, so nothing here proves a real categorization call works.
What is verified is the enforcement logic that runs on whatever a model
returns: exactly-once line coverage, category_id membership, and deposit
category inheritance.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models import Category, User
from app.services import receipt_categorize
from app.services.llm_client import LLMProvider
from app.services.receipt_categorize import (
    CategorizableLine,
    ReceiptCategorizationError,
    _assign_categories,
    categorize_lines,
    categorize_receipt_lines,
)

USER_ID = "categorize-user"


# ---------------------------------------------------------------------------
# _assign_categories -- pure enforcement, no DB, no LLM
# ---------------------------------------------------------------------------

_CAT_A = str(uuid4())
_CAT_B = str(uuid4())
_VALID_IDS = {_CAT_A, _CAT_B}


def _lines(*specs: tuple[str, str, str | None]) -> list[CategorizableLine]:
    """`specs` are (line_ref, kind, parent_line_ref) tuples."""
    return [
        CategorizableLine(
            line_ref=ref, name=f"Item {ref}", raw_text=None, kind=kind, parent_line_ref=parent
        )
        for ref, kind, parent in specs
    ]


def _entry(
    line_id: str, category_id: str, confidence: str = "high", reason: str = "because"
) -> dict:
    return {
        "line_id": line_id,
        "category_id": category_id,
        "confidence": confidence,
        "reason": reason,
    }


def test_happy_path_returns_one_assignment_per_line():
    lines = _lines(("L1", "item", None), ("L2", "item", None))
    payload = {"assignments": [_entry("L1", _CAT_A), _entry("L2", _CAT_B)]}

    result = _assign_categories(lines, payload, _VALID_IDS)

    assert set(result) == {"L1", "L2"}
    assert result["L1"].category_id == receipt_categorize.UUID(_CAT_A)
    assert result["L2"].category_id == receipt_categorize.UUID(_CAT_B)


def test_missing_line_id_raises():
    lines = _lines(("L1", "item", None), ("L2", "item", None))
    payload = {"assignments": [_entry("L1", _CAT_A)]}  # L2 missing

    with pytest.raises(ReceiptCategorizationError, match="L2"):
        _assign_categories(lines, payload, _VALID_IDS)


def test_duplicated_line_id_raises():
    lines = _lines(("L1", "item", None))
    payload = {"assignments": [_entry("L1", _CAT_A), _entry("L1", _CAT_B)]}

    with pytest.raises(ReceiptCategorizationError, match="L1"):
        _assign_categories(lines, payload, _VALID_IDS)


def test_assignment_for_an_unknown_line_id_raises():
    lines = _lines(("L1", "item", None))
    payload = {"assignments": [_entry("L1", _CAT_A), _entry("L99", _CAT_B)]}

    with pytest.raises(ReceiptCategorizationError, match="L99"):
        _assign_categories(lines, payload, _VALID_IDS)


def test_category_id_outside_the_supplied_set_raises():
    lines = _lines(("L1", "item", None))
    outside_id = str(uuid4())
    payload = {"assignments": [_entry("L1", outside_id)]}

    with pytest.raises(ReceiptCategorizationError, match=outside_id):
        _assign_categories(lines, payload, _VALID_IDS)


def test_category_id_outside_the_set_never_falls_through_to_uncategorized():
    """The failure mode that matters most: an invalid category_id must
    raise, never silently resolve to `None`/uncategorized."""
    lines = _lines(("L1", "item", None))
    payload = {"assignments": [_entry("L1", str(uuid4()))]}

    with pytest.raises(ReceiptCategorizationError):
        result = _assign_categories(lines, payload, _VALID_IDS)
        assert result  # unreachable; documents intent if this ever stops raising


def test_invalid_confidence_value_raises():
    lines = _lines(("L1", "item", None))
    payload = {"assignments": [_entry("L1", _CAT_A, confidence="very-sure")]}

    with pytest.raises(ReceiptCategorizationError, match="very-sure"):
        _assign_categories(lines, payload, _VALID_IDS)


def test_deposit_inherits_parent_category_even_when_model_assigns_something_else():
    lines = _lines(("L1", "item", None), ("L2", "deposit", "L1"))
    payload = {
        "assignments": [
            _entry("L1", _CAT_A, confidence="high", reason="it's groceries"),
            # The model assigns the deposit a *different* category and a
            # different confidence/reason -- all of it must be discarded.
            _entry("L2", _CAT_B, confidence="low", reason="not sure what a deposit is"),
        ]
    }

    result = _assign_categories(lines, payload, _VALID_IDS)

    assert result["L2"].category_id == result["L1"].category_id == receipt_categorize.UUID(_CAT_A)
    assert result["L2"].confidence == result["L1"].confidence == "high"
    assert result["L2"].reason == result["L1"].reason == "it's groceries"


def test_deposit_with_unresolvable_parent_raises():
    lines = _lines(("L1", "deposit", "L99"))  # no such parent in this receipt
    payload = {"assignments": [_entry("L1", _CAT_A)]}

    with pytest.raises(ReceiptCategorizationError, match="L99"):
        _assign_categories(lines, payload, _VALID_IDS)


def test_deposit_with_no_parent_line_ref_raises():
    lines = _lines(("L1", "deposit", None))
    payload = {"assignments": [_entry("L1", _CAT_A)]}

    with pytest.raises(ReceiptCategorizationError):
        _assign_categories(lines, payload, _VALID_IDS)


# ---------------------------------------------------------------------------
# categorize_lines -- the LLM call, mocked
# ---------------------------------------------------------------------------


def _seed_expense_category(db_session, name="Groceries", instructions=None) -> Category:
    user = db_session.get(User, USER_ID)
    if user is None:
        db_session.add(User(id=USER_ID, email="cat@test.com", functional_currency="EUR"))
        db_session.flush()
    category = Category(
        user_id=USER_ID,
        name=name,
        category_type="expense",
        categorization_instructions=instructions,
    )
    db_session.add(category)
    db_session.commit()
    return category


def _fake_provider() -> LLMProvider:
    return LLMProvider(
        client=object(),
        model="gpt-4o-mini",
        label="primary",
        supports_vision=False,
        supports_strict_schema=True,
    )


def test_categorize_lines_requires_only_strict_schema_capability(db_session, monkeypatch):
    category = _seed_expense_category(db_session)
    captured_requires = {}

    def _fake_create_llm_clients(db, requires=frozenset()):
        captured_requires["requires"] = requires
        return [_fake_provider()]

    def _fake_call_structured(
        providers, *, messages, schema, schema_name, max_tokens, timeout, **kw
    ):
        return {
            "assignments": [
                {
                    "line_id": "L1",
                    "category_id": str(category.id),
                    "confidence": "high",
                    "reason": "milk",
                }
            ]
        }, "gpt-4o-mini"

    monkeypatch.setattr(receipt_categorize, "create_llm_clients", _fake_create_llm_clients)
    monkeypatch.setattr(receipt_categorize, "call_structured", _fake_call_structured)

    lines = [CategorizableLine("L1", "Milk", None, "item", None)]
    result = categorize_lines(db_session, USER_ID, lines)

    assert captured_requires["requires"] == frozenset({"strict_schema"})
    assert result["L1"].category_id == category.id


def test_categorize_lines_sends_categorization_instructions_verbatim(db_session, monkeypatch):
    instructions = "Only the downtown branch counts as this category."
    category = _seed_expense_category(db_session, instructions=instructions)

    captured = {}

    def _fake_call_structured(
        providers, *, messages, schema, schema_name, max_tokens, timeout, **kw
    ):
        captured["messages"] = messages
        return {
            "assignments": [
                {
                    "line_id": "L1",
                    "category_id": str(category.id),
                    "confidence": "high",
                    "reason": "x",
                }
            ]
        }, "gpt-4o-mini"

    monkeypatch.setattr(
        receipt_categorize,
        "create_llm_clients",
        lambda db, requires=frozenset(): [_fake_provider()],
    )
    monkeypatch.setattr(receipt_categorize, "call_structured", _fake_call_structured)

    categorize_lines(db_session, USER_ID, [CategorizableLine("L1", "Milk", None, "item", None)])

    joined = " ".join(m["content"] for m in captured["messages"])
    assert instructions in joined


def test_categorize_lines_with_no_expense_categories_raises(db_session, monkeypatch):
    db_session.add(User(id=USER_ID, email="cat@test.com", functional_currency="EUR"))
    db_session.commit()

    monkeypatch.setattr(
        receipt_categorize,
        "create_llm_clients",
        lambda db, requires=frozenset(): [_fake_provider()],
    )

    with pytest.raises(ReceiptCategorizationError):
        categorize_lines(db_session, USER_ID, [CategorizableLine("L1", "Milk", None, "item", None)])


def test_categorize_lines_with_no_lines_returns_empty_without_calling_the_model(
    db_session, monkeypatch
):
    called = {"llm": False}

    def _fail_if_called(*a, **kw):
        called["llm"] = True

    monkeypatch.setattr(receipt_categorize, "create_llm_clients", _fail_if_called)

    assert categorize_lines(db_session, USER_ID, []) == {}
    assert called["llm"] is False


# ---------------------------------------------------------------------------
# categorize_receipt_lines -- writes back onto ORM-shaped objects
# ---------------------------------------------------------------------------


class _FakeLineItem:
    """Stands in for `ReceiptLineItem` -- only the attributes
    `categorize_receipt_lines` actually reads/writes."""

    def __init__(self, line_ref, name, kind="item", parent_line_ref=None):
        self.line_ref = line_ref
        self.name = name
        self.raw_text = None
        self.kind = kind
        self.parent_line_ref = parent_line_ref
        self.category_id = None
        self.category_confidence = None
        self.category_reason = None


def test_categorize_receipt_lines_writes_category_fields_onto_the_line_objects(
    db_session, monkeypatch
):
    category = _seed_expense_category(db_session)

    def _fake_call_structured(
        providers, *, messages, schema, schema_name, max_tokens, timeout, **kw
    ):
        return (
            {
                "assignments": [
                    {
                        "line_id": "L1",
                        "category_id": str(category.id),
                        "confidence": "medium",
                        "reason": "dairy",
                    }
                ]
            },
            "gpt-4o-mini",
        )

    monkeypatch.setattr(
        receipt_categorize,
        "create_llm_clients",
        lambda db, requires=frozenset(): [_fake_provider()],
    )
    monkeypatch.setattr(receipt_categorize, "call_structured", _fake_call_structured)

    line = _FakeLineItem("L1", "Milk")
    categorize_receipt_lines(db_session, USER_ID, [line])

    assert line.category_id == category.id
    assert line.category_confidence == "medium"
    assert line.category_reason == "dairy"


def test_categorize_receipt_lines_deposit_line_gets_parent_category(db_session, monkeypatch):
    category = _seed_expense_category(db_session)
    other_category = _seed_expense_category(db_session, name="Other")

    def _fake_call_structured(
        providers, *, messages, schema, schema_name, max_tokens, timeout, **kw
    ):
        return (
            {
                "assignments": [
                    {
                        "line_id": "L1",
                        "category_id": str(category.id),
                        "confidence": "high",
                        "reason": "beer",
                    },
                    {
                        "line_id": "L2",
                        "category_id": str(other_category.id),
                        "confidence": "low",
                        "reason": "?",
                    },
                ]
            },
            "gpt-4o-mini",
        )

    monkeypatch.setattr(
        receipt_categorize,
        "create_llm_clients",
        lambda db, requires=frozenset(): [_fake_provider()],
    )
    monkeypatch.setattr(receipt_categorize, "call_structured", _fake_call_structured)

    item = _FakeLineItem("L1", "Beer")
    deposit = _FakeLineItem("L2", "Deposit", kind="deposit", parent_line_ref="L1")
    categorize_receipt_lines(db_session, USER_ID, [item, deposit])

    assert deposit.category_id == item.category_id == category.id
    assert deposit.category_confidence == item.category_confidence == "high"


def test_categorize_receipt_lines_with_no_lines_is_a_noop(db_session, monkeypatch):
    called = {"llm": False}
    monkeypatch.setattr(
        receipt_categorize, "create_llm_clients", lambda *a, **kw: called.__setitem__("llm", True)
    )
    categorize_receipt_lines(db_session, USER_ID, [])
    assert called["llm"] is False
