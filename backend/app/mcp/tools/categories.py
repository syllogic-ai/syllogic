"""
Category tools for the MCP server.
"""
from typing import Optional

from app.mcp.dependencies import get_db, validate_uuid
from app.models import Category


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
        category = db.query(Category).filter(
            Category.id == category_uuid,
            Category.user_id == user_id
        ).first()

        if not category:
            return None

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


def update_category(
    user_id: str,
    category_id: str,
    description: Optional[str] = None,
    categorization_instructions: Optional[str] = None,
) -> dict:
    """
    Update a category's description and/or categorization_instructions.

    Used by agents to persist learned categorization context so that the AI
    can apply consistent rules on future transactions. Only the provided
    fields are updated; omitted fields are left untouched. Pass an empty
    string to explicitly clear a field.

    Args:
        user_id: The user's ID
        category_id: The category's ID
        description: New description text (optional)
        categorization_instructions: New categorization instructions (optional)

    Returns:
        Dict with success status and updated category, or error message
    """
    if description is None and categorization_instructions is None:
        return {
            "success": False,
            "error": "At least one of description or categorization_instructions must be provided",
        }

    category_uuid = validate_uuid(category_id)
    if not category_uuid:
        return {"success": False, "error": "Invalid category ID format"}

    with get_db() as db:
        category = db.query(Category).filter(
            Category.id == category_uuid,
            Category.user_id == user_id,
        ).first()

        if not category:
            return {"success": False, "error": "Category not found"}

        if category.is_system:
            return {"success": False, "error": "Cannot update system categories"}

        try:
            if description is not None:
                category.description = description or None
            if categorization_instructions is not None:
                category.categorization_instructions = categorization_instructions or None
            db.commit()
            db.refresh(category)
        except Exception as e:
            db.rollback()
            return {"success": False, "error": f"Database error: {str(e)}"}

        return {
            "success": True,
            "category": {
                "id": str(category.id),
                "name": category.name,
                "category_type": category.category_type,
                "color": category.color,
                "icon": category.icon,
                "description": category.description,
                "categorization_instructions": category.categorization_instructions,
                "parent_id": str(category.parent_id) if category.parent_id else None,
                "is_system": category.is_system,
            },
        }


def get_category_tree(user_id: str) -> list[dict]:
    """
    Get categories in a hierarchical tree structure.

    Args:
        user_id: The user's ID

    Returns:
        List of root categories, each with nested 'children' list
    """
    with get_db() as db:
        categories = db.query(Category).filter(
            Category.user_id == user_id
        ).order_by(Category.name).all()

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
                "children": []
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
