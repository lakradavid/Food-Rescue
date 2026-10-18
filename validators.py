"""
validators.py
-------------
Application-level validation functions.

These run BEFORE any data reaches MongoDB, providing clear, user-friendly
error messages. MongoDB's JSON Schema is the last line of defense; these
validators are the first.

Every public function returns a (is_valid: bool, errors: list[str]) tuple
so callers can collect all errors at once and display them together.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from config import (
    FOOD_CATEGORIES,
    QUANTITY_UNITS,
    LISTING_STATUSES,
    CLAIM_STATUSES,
    USER_ROLES,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Primitive helpers
# ─────────────────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s\-]{7,15}$")


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
#  User validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_user(data: dict) -> tuple[bool, list[str]]:
    """
    Validate a new user document.

    Required fields: name, email, role
    Optional fields: phone, location, organization
    """
    errors: list[str] = []

    # name
    name = data.get("name", "")
    if _is_blank(name):
        errors.append("Name is required.")
    elif len(name.strip()) < 2:
        errors.append("Name must be at least 2 characters.")
    elif len(name.strip()) > 100:
        errors.append("Name must not exceed 100 characters.")

    # email
    email = data.get("email", "")
    if _is_blank(email):
        errors.append("Email is required.")
    elif not _EMAIL_RE.match(email.strip()):
        errors.append("Email address is not valid.")

    # role
    role = data.get("role", "")
    if _is_blank(role):
        errors.append("Role is required.")
    elif role not in USER_ROLES:
        errors.append(f"Role must be one of: {', '.join(USER_ROLES)}.")

    # phone (optional)
    phone = data.get("phone")
    if phone and not _PHONE_RE.match(str(phone).strip()):
        errors.append("Phone number format is invalid (7–15 digits, optional + and spaces).")

    # location (optional)
    location = data.get("location")
    if location and len(str(location).strip()) > 200:
        errors.append("Location must not exceed 200 characters.")

    return len(errors) == 0, errors


# ─────────────────────────────────────────────────────────────────────────────
#  Food listing validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_food_listing(data: dict) -> tuple[bool, list[str]]:
    """
    Validate a food listing document before insert or update.

    Required: title, category, quantity, unit, pickup_location,
              prepared_at, pickup_deadline, donor_id
    Optional: description, allergens
    """
    errors: list[str] = []

    # title
    title = data.get("title", "")
    if _is_blank(title):
        errors.append("Food title is required.")
    elif len(title.strip()) < 2:
        errors.append("Food title must be at least 2 characters.")
    elif len(title.strip()) > 150:
        errors.append("Food title must not exceed 150 characters.")

    # category
    category = data.get("category", "")
    if _is_blank(category):
        errors.append("Category is required.")
    elif category not in FOOD_CATEGORIES:
        errors.append(f"Category must be one of: {', '.join(FOOD_CATEGORIES)}.")

    # quantity
    qty = data.get("quantity")
    if qty is None:
        errors.append("Quantity is required.")
    else:
        try:
            qty_f = float(qty)
            if qty_f <= 0:
                errors.append("Quantity must be greater than 0.")
            elif qty_f > 10_000:
                errors.append("Quantity seems unrealistically large (> 10,000). Please verify.")
        except (TypeError, ValueError):
            errors.append("Quantity must be a number.")

    # unit
    unit = data.get("unit", "")
    if _is_blank(unit):
        errors.append("Unit is required.")
    elif unit not in QUANTITY_UNITS:
        errors.append(f"Unit must be one of: {', '.join(QUANTITY_UNITS)}.")

    # pickup_location
    loc = data.get("pickup_location", "")
    if _is_blank(loc):
        errors.append("Pickup location is required.")
    elif len(loc.strip()) < 2:
        errors.append("Pickup location must be at least 2 characters.")

    # donor_id
    if _is_blank(data.get("donor_id")):
        errors.append("Donor ID is required.")

    # prepared_at
    prepared_at = data.get("prepared_at")
    if prepared_at is None:
        errors.append("Preparation date/time is required.")
    elif not isinstance(prepared_at, datetime):
        errors.append("Preparation date/time must be a datetime object.")

    # pickup_deadline
    deadline = data.get("pickup_deadline")
    if deadline is None:
        errors.append("Safe pickup deadline is required.")
    elif not isinstance(deadline, datetime):
        errors.append("Pickup deadline must be a datetime object.")
    else:
        # Deadline must be in the future for new listings
        if deadline <= _now():
            errors.append("Pickup deadline must be in the future.")
        # Deadline must be after preparation time
        if isinstance(prepared_at, datetime) and deadline <= prepared_at:
            errors.append("Pickup deadline must be after the preparation date/time.")

    # allergens (optional list of strings)
    allergens = data.get("allergens")
    if allergens is not None:
        if not isinstance(allergens, list):
            errors.append("Allergens must be a list of strings.")
        elif any(not isinstance(a, str) for a in allergens):
            errors.append("Each allergen entry must be a string.")

    # description (optional)
    desc = data.get("description")
    if desc and len(str(desc)) > 1000:
        errors.append("Description must not exceed 1000 characters.")

    return len(errors) == 0, errors


# ─────────────────────────────────────────────────────────────────────────────
#  Claim validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_claim(data: dict, listing: dict) -> tuple[bool, list[str]]:
    """
    Validate a claim request against both the claim data and the current
    state of the food listing.

    Parameters
    ----------
    data    : claim payload with keys listing_id, claimant_id, claimed_quantity
    listing : the full food_listings document fetched from MongoDB
    """
    errors: list[str] = []

    # claimant_id
    if _is_blank(data.get("claimant_id")):
        errors.append("Claimant ID is required.")

    # listing_id
    if _is_blank(data.get("listing_id")):
        errors.append("Listing ID is required.")

    # claimed_quantity
    qty = data.get("claimed_quantity")
    if qty is None:
        errors.append("Claimed quantity is required.")
    else:
        try:
            qty_f = float(qty)
            if qty_f <= 0:
                errors.append("Claimed quantity must be greater than 0.")
        except (TypeError, ValueError):
            errors.append("Claimed quantity must be a number.")

    # Listing-level checks (server-side – not just UI checks)
    if listing is None:
        errors.append("The food listing does not exist.")
        return False, errors

    # Status check
    if listing.get("status") != "available":
        errors.append(
            f"This listing is currently '{listing.get('status')}' and cannot be claimed."
        )

    # Deadline check
    deadline = listing.get("pickup_deadline")
    if isinstance(deadline, datetime):
        # Make both timezone-aware for comparison
        now = _now()
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if now > deadline:
            errors.append("The safe pickup deadline has passed. This listing cannot be claimed.")

    # Quantity check
    if qty is not None:
        try:
            qty_f = float(qty)
            available = float(listing.get("quantity", 0)) - float(listing.get("claimed_quantity", 0))
            if qty_f > available:
                errors.append(
                    f"Cannot claim {qty_f} {listing.get('unit')}. "
                    f"Only {available:.2f} {listing.get('unit')} available."
                )
        except (TypeError, ValueError):
            pass  # already caught above

    return len(errors) == 0, errors


# ─────────────────────────────────────────────────────────────────────────────
#  Claim status transition validation
# ─────────────────────────────────────────────────────────────────────────────

# Allowed transitions: current_status -> set of allowed next statuses
_CLAIM_TRANSITIONS: dict[str, set[str]] = {
    "pending":   {"confirmed", "cancelled"},
    "confirmed": {"completed", "cancelled"},
    "completed": set(),          # terminal – no further changes
    "cancelled": set(),          # terminal
}


def validate_claim_transition(current: str, new: str) -> tuple[bool, list[str]]:
    """Check whether a claim status transition is allowed."""
    errors: list[str] = []
    if new not in CLAIM_STATUSES:
        errors.append(f"'{new}' is not a valid claim status.")
        return False, errors
    allowed = _CLAIM_TRANSITIONS.get(current, set())
    if new not in allowed:
        errors.append(
            f"Cannot move claim from '{current}' to '{new}'. "
            f"Allowed transitions: {', '.join(allowed) or 'none (terminal state)'}."
        )
    return len(errors) == 0, errors


# ─────────────────────────────────────────────────────────────────────────────
#  Listing status transition validation
# ─────────────────────────────────────────────────────────────────────────────

_LISTING_TRANSITIONS: dict[str, set[str]] = {
    "available": {"reserved", "expired"},
    "reserved":  {"available", "rescued", "expired"},
    "rescued":   set(),   # terminal
    "expired":   set(),   # terminal
}


def validate_listing_transition(current: str, new: str) -> tuple[bool, list[str]]:
    """Check whether a listing status transition is allowed."""
    errors: list[str] = []
    if new not in LISTING_STATUSES:
        errors.append(f"'{new}' is not a valid listing status.")
        return False, errors
    allowed = _LISTING_TRANSITIONS.get(current, set())
    if new not in allowed:
        errors.append(
            f"Cannot move listing from '{current}' to '{new}'. "
            f"Allowed transitions: {', '.join(allowed) or 'none (terminal state)'}."
        )
    return len(errors) == 0, errors
