"""
services/user_service.py
------------------------
Business logic for user management.

The service layer sits between the UI (pages/) and the data layer
(repositories/).  It coordinates validation, hashing, and repo calls
so that pages never talk to MongoDB directly.
"""

from __future__ import annotations

import bcrypt
from pymongo.database import Database

from validators import validate_user
from repositories.user_repo import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_all_users,
    update_user,
    delete_user,
    count_users_by_role,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Registration
# ─────────────────────────────────────────────────────────────────────────────

def register_user(db: Database, form_data: dict) -> tuple[bool, str]:
    """
    Validate → hash password → insert user.

    Returns (True, user_id_str) on success.
    Returns (False, error_message) on failure.
    """
    ok, errors = validate_user(form_data)
    if not ok:
        return False, "  •  " + "\n  •  ".join(errors)

    # Check duplicate email before hashing (fast fail)
    existing = get_user_by_email(db, form_data["email"])
    if existing:
        return False, "A user with this email address already exists."

    # Hash the password if provided; store None otherwise
    password_hash = None
    raw_pw = form_data.get("password", "").strip()
    if raw_pw:
        if len(raw_pw) < 6:
            return False, "Password must be at least 6 characters."
        password_hash = bcrypt.hashpw(raw_pw.encode(), bcrypt.gensalt()).decode()

    payload = {**form_data, "password_hash": password_hash}
    return create_user(db, payload)


def authenticate_user(db: Database, email: str, password: str) -> tuple[bool, str | dict]:
    """
    Simple email + bcrypt authentication.

    Returns (True, user_dict) on success.
    Returns (False, error_message) on failure.
    """
    if not email or not password:
        return False, "Email and password are required."

    user = get_user_by_email(db, email)
    if not user:
        return False, "No account found with that email address."

    stored_hash = user.get("password_hash")
    if not stored_hash:
        # Account was created without a password (e.g. seed data)
        return False, "This account has no password set."

    if not bcrypt.checkpw(password.encode(), stored_hash.encode()):
        return False, "Incorrect password."

    if not user.get("active", True):
        return False, "This account has been deactivated."

    return True, user


# ─────────────────────────────────────────────────────────────────────────────
#  Read helpers  (thin wrappers – keeps pages import-clean)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_user(db: Database, user_id: str) -> dict | None:
    return get_user_by_id(db, user_id)


def fetch_users(db: Database, role: str | None = None) -> list[dict]:
    return get_all_users(db, role=role)


def fetch_donors(db: Database) -> list[dict]:
    return get_all_users(db, role="donor")


def fetch_recipients_and_volunteers(db: Database) -> list[dict]:
    """Return all users who can claim food."""
    users = get_all_users(db, role="recipient") + get_all_users(db, role="volunteer")
    return sorted(users, key=lambda u: u["name"])


def user_role_counts(db: Database) -> dict:
    return count_users_by_role(db)


# ─────────────────────────────────────────────────────────────────────────────
#  Update / Delete
# ─────────────────────────────────────────────────────────────────────────────

def edit_user(db: Database, user_id: str, updates: dict) -> tuple[bool, str]:
    return update_user(db, user_id, updates)


def deactivate_user(db: Database, user_id: str) -> tuple[bool, str]:
    return delete_user(db, user_id)
