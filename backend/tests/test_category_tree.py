"""Tests for `app.services.category_tree.serialize_for_prompt` (Phase 5.1 of
the receipt-ingestion rework). See
docs/specs/receipt-ingestion-implementation.md 5.1 and its "Phase 5
checkpoint": the serialized tree contains `categorization_instructions`
verbatim, contains no income categories (when `types={"expense"}`), and
honours `exclude_category_ids`.

This module was extracted out of `app/mcp/resources.py`'s in-line tree walk
so that walk isn't duplicated for stage 2 categorization -- the MCP-resource
side of the contract (the nested-tree, all-types shape) is covered by
`test_mcp_resources_and_prompts.py::test_categories_resource_carries_the_users_own_rules`,
which must keep passing unchanged.
"""

from __future__ import annotations

import json

from app.models import Category, User
from app.services import category_tree

USER_ID = "category-tree-user"


def _user(db_session) -> User:
    user = User(id=USER_ID, email="tree@test.com", functional_currency="EUR")
    db_session.add(user)
    db_session.flush()
    return user


def test_leaves_only_includes_categorization_instructions_verbatim(db_session):
    _user(db_session)
    verbatim_instructions = (
        "Supermarkets only.\nNever the pharmacy chain, even though it shares "
        "a parent company -- see note from 2026-03."
    )
    parent = Category(user_id=USER_ID, name="Food", category_type="expense")
    db_session.add(parent)
    db_session.flush()
    db_session.add(
        Category(
            user_id=USER_ID,
            name="Groceries",
            category_type="expense",
            parent_id=parent.id,
            categorization_instructions=verbatim_instructions,
        )
    )
    db_session.commit()

    result = json.loads(
        category_tree.serialize_for_prompt(
            db_session, USER_ID, types=frozenset({"expense"}), leaves_only=True
        )
    )

    groceries = next(n for n in result if n["name"] == "Groceries")
    assert groceries["categorization_instructions"] == verbatim_instructions


def test_leaves_only_excludes_branch_nodes(db_session):
    _user(db_session)
    parent = Category(user_id=USER_ID, name="Food", category_type="expense")
    db_session.add(parent)
    db_session.flush()
    db_session.add(
        Category(user_id=USER_ID, name="Groceries", category_type="expense", parent_id=parent.id)
    )
    db_session.commit()

    result = json.loads(
        category_tree.serialize_for_prompt(
            db_session, USER_ID, types=frozenset({"expense"}), leaves_only=True
        )
    )

    names = {n["name"] for n in result}
    assert "Groceries" in names
    assert "Food" not in names  # has a child -> not a leaf
    assert all("children" not in n for n in result)


def test_leaves_only_default_types_excludes_income_categories(db_session):
    _user(db_session)
    db_session.add_all(
        [
            Category(user_id=USER_ID, name="Groceries", category_type="expense"),
            Category(user_id=USER_ID, name="Salary", category_type="income"),
            Category(user_id=USER_ID, name="Internal transfer", category_type="transfer"),
        ]
    )
    db_session.commit()

    result = json.loads(category_tree.serialize_for_prompt(db_session, USER_ID))

    names = {n["name"] for n in result}
    assert names == {"Groceries"}


def test_exclude_category_ids_filters_a_category_out(db_session):
    _user(db_session)
    keep = Category(user_id=USER_ID, name="Groceries", category_type="expense")
    drop = Category(user_id=USER_ID, name="Legacy Groceries", category_type="expense")
    db_session.add_all([keep, drop])
    db_session.commit()

    result = json.loads(
        category_tree.serialize_for_prompt(
            db_session,
            USER_ID,
            types=frozenset({"expense"}),
            leaves_only=True,
            exclude_category_ids=frozenset({drop.id}),
        )
    )

    names = {n["name"] for n in result}
    assert names == {"Groceries"}


def test_nested_tree_shape_used_by_the_mcp_resource(db_session):
    """`leaves_only=False, types=ALL_CATEGORY_TYPES` is exactly what
    `syllogic://categories` calls with -- the nested `children` shape must
    survive the extraction out of resources.py."""
    _user(db_session)
    parent = Category(user_id=USER_ID, name="Food", category_type="expense")
    db_session.add(parent)
    db_session.flush()
    db_session.add(
        Category(
            user_id=USER_ID,
            name="Groceries",
            category_type="expense",
            parent_id=parent.id,
            categorization_instructions="Supermarkets only.",
        )
    )
    db_session.add(Category(user_id=USER_ID, name="Salary", category_type="income"))
    db_session.commit()

    result = json.loads(
        category_tree.serialize_for_prompt(
            db_session,
            USER_ID,
            types=category_tree.ALL_CATEGORY_TYPES,
            leaves_only=False,
        )
    )

    names = {n["name"] for n in result}
    assert "Food" in names
    assert "Salary" in names  # all types included this time
    food = next(n for n in result if n["name"] == "Food")
    assert [c["name"] for c in food["children"]] == ["Groceries"]
    assert food["children"][0]["categorization_instructions"] == "Supermarkets only."


def test_a_category_with_no_categorization_instructions_serializes_as_null(db_session):
    _user(db_session)
    db_session.add(Category(user_id=USER_ID, name="Groceries", category_type="expense"))
    db_session.commit()

    result = json.loads(category_tree.serialize_for_prompt(db_session, USER_ID))
    assert result[0]["categorization_instructions"] is None
