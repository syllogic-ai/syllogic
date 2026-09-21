"""
Category tools for the MCP server.
"""

from typing import Optional

from app.mcp.dependencies import get_db, require_uuid, validate_uuid
from app.mcp.errors import missing_argument, not_found, raise_database_error
from app.mcp.tools._writes import mutation_result, preview_or_commit, snapshot
from app.models import Category
from app.services import category_instruction_lint


# The fields update_category can actually change. Snapshotted before and
# after so a no-op reports itself as one.
EDITABLE_FIELDS = ("description", "categorization_instructions")


def _serialize_category(category) -> dict:
    """The full category shape, including the two editable fields.

    `list_categories` deliberately omits `categorization_instructions` --
    they run to paragraphs and there is one per category.
    """
    return {
        "id": str(category.id),
        "name": category.name,
        "category_type": category.category_type,
        "color": category.color,
        "icon": category.icon,
        "description": category.description,
        "categorization_instructions": category.categorization_instructions,
        "parent_id": str(category.parent_id) if category.parent_id else None,
        "is_system": category.is_system,
        "created_at": category.created_at.isoformat() if category.created_at else None,
    }


def _instruction_warnings(db, user_id: str, category) -> dict:
    """`{"instruction_warnings": [...]}` when the instructions name a
    category that does not resolve, `{}` otherwise.

    Spread into `mutation_result`, so a clean write is shaped exactly as it
    was before this check existed. The lint itself never raises (see
    `app/services/category_instruction_lint.py`): instructions that route to
    a name the tree no longer has are worth flagging, and are never worth
    refusing a write the user asked for.
    """
    findings = category_instruction_lint.lint_category(db, user_id, category)
    if not findings:
        return {}
    return {"instruction_warnings": category_instruction_lint.warning_messages(findings)}


def categorization_instructions_map(user_id: str) -> dict[str, str | None]:
    """{category_id: categorization_instructions} for every category.

    One query. `list_categories` and `get_category_tree` leave the field out
    because it runs to paragraphs and there is one per category, but the
    categories *resource* wants all of them at once -- those instructions are
    the rules the user has taught the system, and an agent that has not read
    them will re-derive them badly.
    """
    with get_db() as db:
        return {
            str(cid): instructions
            for cid, instructions in db.query(
                Category.id, Category.categorization_instructions
            ).filter(Category.user_id == user_id)
        }


def _category_candidates(db, user_id: str) -> list[tuple[str, str]]:
    """(name, id) pairs for a not_found message.

    Takes the caller's session: the lookup that just missed already has one
    open, and a failed read should not cost a second connection.
    """
    return [
        (name, str(cid))
        for cid, name in db.query(Category.id, Category.name)
        .filter(Category.user_id == user_id)
        .order_by(Category.name)
        .all()
    ]


def list_categories(user_id: str, category_type: Optional[str] = None) -> list[dict]:
    """
    List all categories for a user.

    Args:
        user_id: The user's ID
        category_type: Filter by type (expense, income, transfer) - optional

    Returns:
        List of category dictionaries with id, name, type, color, icon, parent info
    """
    with get_db() as db:
        query = db.query(Category).filter(Category.user_id == user_id)

        if category_type:
            query = query.filter(Category.category_type == category_type)

        categories = query.order_by(Category.name).all()

        return [
            {
                "id": str(cat.id),
                "name": cat.name,
                "category_type": cat.category_type,
                "color": cat.color,
                "icon": cat.icon,
                "description": cat.description,
                "parent_id": str(cat.parent_id) if cat.parent_id else None,
                "is_system": cat.is_system,
                "created_at": cat.created_at.isoformat() if cat.created_at else None,
            }
            for cat in categories
        ]


def get_category(user_id: str, category_id: str) -> dict | None:
    """
    Get a single category by ID.

    Args:
        user_id: The user's ID
        category_id: The category's ID

    Returns:
        Category dictionary or None if not found
    """
    category_uuid = validate_uuid(category_id)
    if not category_uuid:
        return None

    with get_db() as db:
        category = (
            db.query(Category)
            .filter(Category.id == category_uuid, Category.user_id == user_id)
            .first()
        )

        if not category:
            return None

        return _serialize_category(category)


def update_category(
    user_id: str,
    category_id: str,
    description: Optional[str] = None,
    categorization_instructions: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Update a category's description and/or categorization_instructions.

    Used by agents to persist learned categorization context so that the AI
    can apply consistent rules on future transactions. Only the provided
    fields are updated; omitted fields are left untouched. Pass an empty
    string to explicitly clear a field. System categories are editable here
    because description/instructions are user-tailored context, not
    structural identity.

    Args:
        user_id: The user's ID
        category_id: The category's ID
        description: New description text (optional)
        categorization_instructions: New categorization instructions (optional)
        dry_run: Preview the change without committing it (default False)

    Returns:
        Dict with `changed`, `before`, `after`, `fields_changed` and the
        serialized `category`. `changed` is False when the values were
        already what was asked for. Raises ToolError on invalid input or an
        unknown category_id.

        Carries `instruction_warnings` **only when the new instructions name
        a category that does not exist** -- a renamed or deleted target the
        instructions still route to, which degrades every categorization
        that reads them and is otherwise invisible. The check is a heuristic
        over prose (see `category_instruction_lint`), so it warns and the
        write goes through regardless; the key is absent on a clean write so
        the usual response stays lean.
    """
    if description is None and categorization_instructions is None:
        raise missing_argument(
            "description or categorization_instructions",
            "at least one must be provided",
        )

    category_uuid = require_uuid(category_id, "category_id")

    with get_db() as db:
        category = (
            db.query(Category)
            .filter(
                Category.id == category_uuid,
                Category.user_id == user_id,
            )
            .first()
        )

        if not category:
            raise not_found(
                "category",
                category_id,
                candidates=_category_candidates(db, user_id),
                tool="list_categories",
            )

        before = snapshot(category, EDITABLE_FIELDS)

        try:
            if description is not None:
                category.description = description or None
            if categorization_instructions is not None:
                category.categorization_instructions = categorization_instructions or None

            return preview_or_commit(
                db,
                dry_run,
                lambda: mutation_result(
                    before,
                    snapshot(category, EDITABLE_FIELDS),
                    category=_serialize_category(category),
                    # Built inside the response callback so the lint reads
                    # the instructions this call just set (and resolves them
                    # against the tree as it stands now), on a preview as
                    # well as on a commit.
                    **_instruction_warnings(db, user_id, category),
                ),
            )
        except Exception as e:
            db.rollback()
            raise_database_error("update_category", e)


def get_category_tree(user_id: str) -> list[dict]:
    """
    Get categories in a hierarchical tree structure.

    Args:
        user_id: The user's ID

    Returns:
        List of root categories, each with nested 'children' list
    """
    with get_db() as db:
        categories = (
            db.query(Category).filter(Category.user_id == user_id).order_by(Category.name).all()
        )

        # Build lookup map
        cat_map = {}
        for cat in categories:
            cat_map[str(cat.id)] = {
                "id": str(cat.id),
                "name": cat.name,
                "category_type": cat.category_type,
                "color": cat.color,
                "icon": cat.icon,
                "description": cat.description,
                "parent_id": str(cat.parent_id) if cat.parent_id else None,
                "is_system": cat.is_system,
                "children": [],
            }

        # Build tree structure
        roots = []
        for cat_id, cat_data in cat_map.items():
            parent_id = cat_data["parent_id"]
            if parent_id and parent_id in cat_map:
                cat_map[parent_id]["children"].append(cat_data)
            else:
                roots.append(cat_data)

        return roots
