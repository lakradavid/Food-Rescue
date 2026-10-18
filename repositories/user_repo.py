"""
repositories/user_repo.py
--------------------------
All direct MongoDB operations for the `users` collection.

Design choice – referencing vs embedding:
  User data (name, email, role) is stored in a separate `users` collection
  and referenced by ObjectId in listings and claims.  This avoids data
  duplication: if a user updates their name or phone number, every listing
  and claim that references them automatically reflects the change on lookup.
  The trade-off is an extra query (or $lookup) whenever we need full user
  details alongside a listing.  Given the modest scale of this application
  and the benefit of a single source of truth, referencing is the right call.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
#  CRUD
# ─────────────────────────────────────────────────────────────────────────────

def create_user(db: Database, data: dict) -> tuple[bool, str]:
    """
    Insert a new user document.

    Returns (True, str(inserted_id)) on success.
    Returns (False, error_message) on failure.
    """
    doc = {
        "name":         data["name"].strip(),
        "email":        data["email"].strip().lower(),
        "role":         data["role"],
        "phone":        data.get("phone", "").strip() or None,
        "location":     data.get("location", "").strip() or None,
        "organization": data.get("organization", "").strip() or None,
        "created_at":   _now(),
    }
    # Optionally store hashed password if provided
    if data.get("password_hash"):
        doc["password_hash"] = data["password_hash"]

    try:
        result = db.users.insert_one(doc)
        return True, str(result.inserted_id)
    except DuplicateKeyError:
        return False, "A user with this email address already exists."
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


def get_user_by_id(db: Database, user_id: str) -> Optional[dict]:
    """Fetch a single user by their ObjectId string. Returns None if not found."""
    try:
        return db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def get_user_by_email(db: Database, email: str) -> Optional[dict]:
    """Fetch a user by email (case-insensitive). Returns None if not found."""
    return db.users.find_one({"email": email.strip().lower()})


def get_all_users(db: Database, role: Optional[str] = None) -> list[dict]:
    """
    Return all users, optionally filtered by role.
    Sorted alphabetically by name.
    """
    query = {}
    if role:
        query["role"] = role
    return list(db.users.find(query).sort("name", 1))


def update_user(db: Database, user_id: str, updates: dict) -> tuple[bool, str]:
    """
    Update allowed user fields: name, phone, location, organization.
    Email and role changes are intentionally restricted here.
    """
    allowed_fields = {"name", "phone", "location", "organization"}
    safe_updates = {k: v for k, v in updates.items() if k in allowed_fields}
    if not safe_updates:
        return False, "No valid fields to update."

    safe_updates["updated_at"] = _now()
    try:
        result = db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": safe_updates},
        )
        if result.matched_count == 0:
            return False, "User not found."
        return True, "User updated successfully."
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


def delete_user(db: Database, user_id: str) -> tuple[bool, str]:
    """
    Soft-delete: mark the user as inactive rather than removing the document.
    This preserves referential integrity for existing listings and claims.
    """
    try:
        result = db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"active": False, "updated_at": _now()}},
        )
        if result.matched_count == 0:
            return False, "User not found."
        return True, "User deactivated."
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


def count_users_by_role(db: Database) -> dict:
    """Return a dict of {role: count} for all roles."""
    pipeline = [
        {"$group": {"_id": "$role", "count": {"$sum": 1}}},
    ]
    return {doc["_id"]: doc["count"] for doc in db.users.aggregate(pipeline)}
