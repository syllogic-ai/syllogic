"""Tests for `app.services.category_instruction_lint` (Phase 8.1 of the
receipt-ingestion rework). See
docs/specs/receipt-ingestion-implementation.md 8.1 and
docs/specs/receipt-ingestion.md Part 8.1.

Two halves. The first pins the heuristic itself -- what counts as a
reference, and more importantly what does not, since the instructions are
prose and a lint that cries wolf gets ignored. The second pins the two
surfaces the spec asks for: a startup log line, and a warning on the write
in `update_category`, where the user is still there to fix it.

The one thing every test here shares is that nothing raises. A hygiene
check that can fail a boot or reject a write is worse than no check.
"""

from __future__ import annotations

import logging

import pytest

from app.database import SessionLocal
from app.mcp.tools.categories import update_category
from app.models import Category, User
from app.services import category_instruction_lint as lint

USER_ID = "instruction-lint-user"
OTHER_USER_ID = "instruction-lint-other-user"


def _user(db_session, user_id: str = USER_ID) -> User:
    user = User(id=user_id, email=f"{user_id}@test.com", functional_currency="EUR")
    db_session.add(user)
    db_session.flush()
    return user


def _category(db_session, name: str, instructions: str | None = None, **kwargs) -> Category:
    category = Category(
        user_id=kwargs.pop("user_id", USER_ID),
        name=name,
        category_type=kwargs.pop("category_type", "expense"),
        categorization_instructions=instructions,
        **kwargs,
    )
    db_session.add(category)
    db_session.flush()
    return category


def _references(findings) -> set[str]:
    return {finding.reference for finding in findings}


# ---------------------------------------------------------------------------
# The heuristic
# ---------------------------------------------------------------------------


def test_a_reference_that_resolves_is_not_reported(db_session):
    _user(db_session)
    _category(db_session, "Dining")
    _category(
        db_session,
        "Groceries",
        "Supermarket receipts only. Anything eaten on the premises goes to 'Dining'.",
    )
    db_session.commit()

    assert lint.lint_user(db_session, USER_ID) == []


def test_a_dangling_quoted_reference_is_reported(db_session):
    _user(db_session)
    groceries = _category(
        db_session,
        "Groceries",
        "Supermarket receipts only. Anything eaten on the premises goes to 'Eating Out'.",
    )
    db_session.commit()

    findings = lint.lint_user(db_session, USER_ID)

    assert _references(findings) == {"Eating Out"}
    assert findings[0].kind == "quoted"
    assert findings[0].category_id == str(groceries.id)
    assert findings[0].category_name == "Groceries"


def test_a_dangling_title_cased_reference_is_reported(db_session):
    _user(db_session)
    _category(db_session, "Groceries", "Bulk supermarket runs. Cleaning products go to Household.")
    db_session.commit()

    findings = lint.lint_user(db_session, USER_ID)

    assert _references(findings) == {"Household"}
    assert findings[0].kind == "title-cased"


def test_a_multi_word_title_cased_reference_is_reported_without_a_cue(db_session):
    """Multi-word Title Case is the shape of a category name and is rare in
    prose, so it does not need a routing phrase in front of it to count."""
    _user(db_session)
    _category(db_session, "Groceries", "Cleaning products belong under Home Improvement.")
    db_session.commit()

    assert _references(lint.lint_user(db_session, USER_ID)) == {"Home Improvement"}


def test_ordinary_prose_does_not_produce_a_flood_of_false_positives(db_session):
    """Sentence-initial capitals, merchants and acronyms are all capitalised
    and none of them is a reference. This is the case the heuristic exists to
    stay quiet on."""
    _user(db_session)
    _category(db_session, "Dining")
    _category(
        db_session,
        "Groceries",
        "Supermarkets only.\n"
        "Never the pharmacy chain, even though it shares a parent company.\n"
        "Anything from Lidl belongs here. Bulk buys too, including VAT-only lines.\n"
        "Receipts from the bakery counter count. Don't split them out.\n"
        "Dining is separate.",
    )
    db_session.commit()

    assert lint.lint_user(db_session, USER_ID) == []


def test_an_apostrophe_is_not_read_as_a_quote(db_session):
    _user(db_session)
    _category(db_session, "Groceries", "Don't use this for fuel; that isn't right.")
    db_session.commit()

    assert lint.lint_user(db_session, USER_ID) == []


def test_a_quoted_sentence_is_not_read_as_a_name(db_session):
    _user(db_session)
    _category(
        db_session,
        "Groceries",
        'The receipt often says "Thank you for shopping with us, see you soon!" -- ignore it.',
    )
    db_session.commit()

    assert lint.lint_user(db_session, USER_ID) == []


def test_a_reference_written_as_a_path_resolves_on_its_leaf(db_session):
    _user(db_session)
    food = _category(db_session, "Food")
    _category(db_session, "Dining", parent_id=food.id)
    _category(db_session, "Groceries", "Meals out go to Food > Dining, never here.")
    db_session.commit()

    assert lint.lint_user(db_session, USER_ID) == []


def test_the_same_dangling_name_repeated_is_one_finding(db_session):
    _user(db_session)
    _category(
        db_session,
        "Groceries",
        "Meals out go to 'Eating Out'. Takeaway is Eating Out too. Anything delivered: Eating Out.",
    )
    db_session.commit()

    findings = lint.lint_user(db_session, USER_ID)
    assert len(findings) == 1
    assert findings[0].reference == "Eating Out"


@pytest.mark.parametrize(
    "instructions",
    [
        None,
        "",
        "   \n\t ",
        "''",
        '"',
        "-- -- --",
        "‘’“”",
        "A" * 5000,
        "Groceries " * 500,
    ],
)
def test_malformed_or_empty_instructions_never_raise(instructions):
    assert (
        lint.lint_instructions(
            instructions,
            {"groceries"},
            category_id="ignored",
            category_name="Groceries",
        )
        is not None
    )


def test_lint_user_returns_empty_rather_than_raising_when_the_query_fails():
    """The contract the two callers rely on: a broken lint is indistinguishable
    from a clean one, because neither gives the user anything to do."""

    class _ExplodingSession:
        def query(self, *args, **kwargs):
            raise RuntimeError("database is on fire")

    assert lint.lint_user(_ExplodingSession(), USER_ID) == []


def test_scoping_is_per_user(db_session):
    """Category names are per-user, so a name that resolves in someone else's
    tree is still dangling in this one."""
    _user(db_session)
    _user(db_session, OTHER_USER_ID)
    _category(db_session, "Household", user_id=OTHER_USER_ID)
    _category(db_session, "Groceries", "Cleaning products go to Household.")
    db_session.commit()

    assert _references(lint.lint_user(db_session, USER_ID)) == {"Household"}
    assert lint.lint_user(db_session, OTHER_USER_ID) == []


# ---------------------------------------------------------------------------
# The two surfaces
# ---------------------------------------------------------------------------


def test_update_category_returns_a_warning_for_a_dangling_reference(db_session):
    _user(db_session)
    category = _category(db_session, "Groceries")
    db_session.commit()

    result = update_category(
        USER_ID,
        str(category.id),
        categorization_instructions="Cleaning products go to 'Household'.",
    )

    assert result["changed"] is True
    assert result["committed"] is True
    assert any("Household" in warning for warning in result["instruction_warnings"])


def test_update_category_stays_silent_when_every_reference_resolves(db_session):
    _user(db_session)
    _category(db_session, "Household")
    category = _category(db_session, "Groceries")
    db_session.commit()

    result = update_category(
        USER_ID,
        str(category.id),
        categorization_instructions="Cleaning products go to 'Household'.",
    )

    assert "instruction_warnings" not in result


def test_update_category_still_writes_the_instructions_it_warned_about(db_session):
    """Warn, never fail: the write the user asked for goes through."""
    _user(db_session)
    category = _category(db_session, "Groceries")
    db_session.commit()

    instructions = "Cleaning products go to 'Household'."
    update_category(USER_ID, str(category.id), categorization_instructions=instructions)

    db_session.expire_all()
    stored = db_session.query(Category).filter(Category.id == category.id).first()
    assert stored.categorization_instructions == instructions


def test_update_category_warns_on_a_dry_run_too(db_session):
    """The preview is where a warning is cheapest to act on."""
    _user(db_session)
    category = _category(db_session, "Groceries")
    db_session.commit()

    result = update_category(
        USER_ID,
        str(category.id),
        categorization_instructions="Cleaning products go to 'Household'.",
        dry_run=True,
    )

    assert result["committed"] is False
    assert any("Household" in warning for warning in result["instruction_warnings"])


def test_startup_logs_a_warning_naming_the_dangling_reference(db_session, caplog):
    _user(db_session)
    _category(db_session, "Groceries", "Cleaning products go to 'Household'.")
    db_session.commit()

    with caplog.at_level(logging.INFO, logger=lint.__name__):
        lint.log_dangling_references(SessionLocal)

    records = [record for record in caplog.records if record.name == lint.__name__]
    assert any(record.levelno == logging.WARNING for record in records)
    assert "Household" in "".join(record.getMessage() for record in records)


def test_startup_says_so_when_nothing_is_dangling(db_session, caplog):
    _user(db_session)
    _category(db_session, "Household")
    _category(db_session, "Groceries", "Cleaning products go to 'Household'.")
    db_session.commit()

    with caplog.at_level(logging.INFO, logger=lint.__name__):
        lint.log_dangling_references(SessionLocal)

    records = [record for record in caplog.records if record.name == lint.__name__]
    assert records and all(record.levelno == logging.INFO for record in records)


def test_startup_never_raises_when_the_database_is_unreachable(caplog):
    def _explode():
        raise RuntimeError("connection refused")

    with caplog.at_level(logging.DEBUG, logger=lint.__name__):
        lint.log_dangling_references(_explode)  # must not raise
