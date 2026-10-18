"""
services/listing_service.py
----------------------------
Business logic for food listing management.

Coordinates:
  - Application-level validation (validators.py)
  - Expiry enforcement (run on every page load)
  - CRUD via listing_repo
  - Status transition rules
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pymongo.database import Database

from validators import validate_food_listing, validate_listing_transition
from repositories.listing_repo import (
    create_listing,
    get_listing_by_id,
    get_listings,
    get_listings_with_donor,
    update_listing,
    update_listing_status,
    delete_listing,
    expire_overdue_listings,
    increment_claimed_quantity,
    release_claimed_quantity,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
#  Expiry sweep (run at startup and on demand)
# ─────────────────────────────────────────────────────────────────────────────

def sweep_expired_listings(db: Database) -> int:
    """
    Mark overdue listings as 'expired'.
    Returns the number of listings that were just expired.
    """
    return expire_overdue_listings(db)


# ─────────────────────────────────────────────────────────────────────────────
#  Create
# ─────────────────────────────────────────────────────────────────────────────

def add_listing(db: Database, form_data: dict) -> tuple[bool, str]:
    """
    Validate and insert a new food listing.
    Returns (True, listing_id) or (False, error_message).
    """
    ok, errors = validate_food_listing(form_data)
    if not ok:
        return False, "  •  " + "\n  •  ".join(errors)
    return create_listing(db, form_data)


# ─────────────────────────────────────────────────────────────────────────────
#  Read
# ─────────────────────────────────────────────────────────────────────────────

def fetch_listing(db: Database, listing_id: str) -> Optional[dict]:
    return get_listing_by_id(db, listing_id)


def fetch_active_listings(
    db: Database,
    category: Optional[str] = None,
    location: Optional[str] = None,
) -> list[dict]:
    """All currently available (non-expired) listings, optionally filtered."""
    return get_listings(db, only_active=True, category=category, location=location)


def fetch_donor_listings(db: Database, donor_id: str) -> list[dict]:
    """All listings posted by a specific donor."""
    return get_listings(db, donor_id=donor_id)


def fetch_listings_for_display(db: Database, filter_query: dict = None) -> list[dict]:
    """Listings with donor name joined in (for browse pages)."""
    return get_listings_with_donor(db, query_filter=filter_query or {})


def fetch_all_listings(db: Database, status: Optional[str] = None) -> list[dict]:
    return get_listings(db, status=status)


# ─────────────────────────────────────────────────────────────────────────────
#  Update
# ─────────────────────────────────────────────────────────────────────────────

def edit_listing(db: Database, listing_id: str, updates: dict, donor_id: str) -> tuple[bool, str]:
    """
    Edit listing fields. Verifies the requesting donor owns the listing
    and that the listing is in an editable state.
    """
    listing = get_listing_by_id(db, listing_id)
    if not listing:
        return False, "Listing not found."
    if str(listing["donor_id"]) != donor_id:
        return False, "You can only edit your own listings."
    if listing["status"] not in ("available",):
        return False, f"Cannot edit a listing with status '{listing['status']}'."

    # Re-validate the merged document
    merged = {**listing, **updates}
    # Convert ObjectId donor_id to str for validator
    merged["donor_id"] = str(merged["donor_id"])
    ok, errors = validate_food_listing(merged)
    if not ok:
        return False, "  •  " + "\n  •  ".join(errors)

    return update_listing(db, listing_id, updates)


def change_listing_status(
    db: Database, listing_id: str, new_status: str
) -> tuple[bool, str]:
    """Change listing status with transition validation."""
    listing = get_listing_by_id(db, listing_id)
    if not listing:
        return False, "Listing not found."
    ok, errors = validate_listing_transition(listing["status"], new_status)
    if not ok:
        return False, errors[0]
    return update_listing_status(db, listing_id, new_status)


# ─────────────────────────────────────────────────────────────────────────────
#  Delete
# ─────────────────────────────────────────────────────────────────────────────

def remove_listing(db: Database, listing_id: str, donor_id: str) -> tuple[bool, str]:
    return delete_listing(db, listing_id, donor_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Quantity helpers (used by claim_service)
# ─────────────────────────────────────────────────────────────────────────────

def reserve_quantity(db: Database, listing_id: str, amount: float) -> tuple[bool, str]:
    return increment_claimed_quantity(db, listing_id, amount)


def unreserve_quantity(db: Database, listing_id: str, amount: float) -> tuple[bool, str]:
    return release_claimed_quantity(db, listing_id, amount)


def available_quantity(listing: dict) -> float:
    """Compute remaining claimable quantity from a listing document."""
    total = float(listing.get("quantity", 0))
    claimed = float(listing.get("claimed_quantity", 0))
    return max(0.0, total - claimed)
