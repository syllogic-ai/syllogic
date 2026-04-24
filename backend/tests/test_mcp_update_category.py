"""
Tests for the update_category MCP tool.

Exercises the tool function directly against the database (no HTTP),
mirroring the setup style used in test_categorizer.py.
"""
import os
import sys
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine
from app.models import Category
from app.db_helpers import get_or_create_system_user
from app.mcp.tools.categories import update_category


def _seed_category(is_system: bool = False) -> tuple[str, str]:
    """Create a user + category, return (user_id, category_id)."""
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
        user = get_or_create_system_user(db)
        user_id = str(user.id)

        # Use a unique name to avoid colliding with the (user_id, name, parent_id)
        # unique constraint across repeated test runs.
        cat = Category(
            user_id=user_id,
            name=f"UpdateTest-{uuid.uuid4().hex[:8]}",
            category_type="expense",
            is_system=is_system,
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)
        return user_id, str(cat.id)
    finally:
        db.close()


def _cleanup(category_id: str) -> None:
    db = SessionLocal()
    try:
        cat = db.query(Category).filter(Category.id == uuid.UUID(category_id)).first()
        if cat:
            db.delete(cat)
            db.commit()
    finally:
        db.close()


def test_update_category_sets_both_fields() -> None:
    user_id, cat_id = _seed_category()
    try:
        result = update_category(
            user_id,
            cat_id,
            description="Day-to-day grocery shopping",
            categorization_instructions="Assign when merchant is a supermarket chain.",
        )
        assert result["success"] is True, result
        assert result["category"]["description"] == "Day-to-day grocery shopping"
        assert (
            result["category"]["categorization_instructions"]
            == "Assign when merchant is a supermarket chain."
        )

        # Round-trip through DB.
        db = SessionLocal()
        try:
            cat = db.query(Category).filter(Category.id == uuid.UUID(cat_id)).first()
            assert cat.description == "Day-to-day grocery shopping"
            assert cat.categorization_instructions == "Assign when merchant is a supermarket chain."
        finally:
            db.close()
        print("✓ update_category sets both fields")
    finally:
        _cleanup(cat_id)


def test_update_category_partial_update_preserves_other_field() -> None:
    user_id, cat_id = _seed_category()
    try:
        update_category(
            user_id,
            cat_id,
            description="initial description",
            categorization_instructions="initial instructions",
        )
        result = update_category(user_id, cat_id, description="updated description")
        assert result["success"] is True
        assert result["category"]["description"] == "updated description"
        # Instructions should be untouched.
        assert result["category"]["categorization_instructions"] == "initial instructions"
        print("✓ update_category preserves unspecified fields")
    finally:
        _cleanup(cat_id)


def test_update_category_empty_string_clears_field() -> None:
    user_id, cat_id = _seed_category()
    try:
        update_category(user_id, cat_id, description="something")
        result = update_category(user_id, cat_id, description="")
        assert result["success"] is True
        assert result["category"]["description"] is None
        print("✓ update_category clears field when passed empty string")
    finally:
        _cleanup(cat_id)


def test_update_category_requires_at_least_one_field() -> None:
    user_id, cat_id = _seed_category()
    try:
        result = update_category(user_id, cat_id)
        assert result["success"] is False
        assert "at least one" in result["error"].lower()
        print("✓ update_category rejects no-op calls")
    finally:
        _cleanup(cat_id)


def test_update_category_rejects_invalid_uuid() -> None:
    user_id, cat_id = _seed_category()
    try:
        result = update_category(user_id, "not-a-uuid", description="x")
        assert result["success"] is False
        assert "invalid" in result["error"].lower()
        print("✓ update_category rejects invalid UUID")
    finally:
        _cleanup(cat_id)


def test_update_category_rejects_foreign_user() -> None:
    user_id, cat_id = _seed_category()
    try:
        other_user = f"user_{uuid.uuid4().hex}"
        result = update_category(other_user, cat_id, description="x")
        assert result["success"] is False
        assert "not found" in result["error"].lower()
        print("✓ update_category rejects access from foreign user")
    finally:
        _cleanup(cat_id)


def test_update_category_rejects_system_category() -> None:
    user_id, cat_id = _seed_category(is_system=True)
    try:
        result = update_category(user_id, cat_id, description="x")
        assert result["success"] is False
        assert "system" in result["error"].lower()
        print("✓ update_category refuses to modify system categories")
    finally:
        _cleanup(cat_id)


if __name__ == "__main__":
    test_update_category_sets_both_fields()
    test_update_category_partial_update_preserves_other_field()
    test_update_category_empty_string_clears_field()
    test_update_category_requires_at_least_one_field()
    test_update_category_rejects_invalid_uuid()
    test_update_category_rejects_foreign_user()
    test_update_category_rejects_system_category()
    print("All update_category tests passed.")
