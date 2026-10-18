"""
services/claim_service.py
--------------------------
Business logic for food claims and rescue record creation.

The critical sequence for claiming food:
  1.  Fetch listing and validate claim data (server-side).
  2.  Atomically reserve quantity on the listing (increment_claimed_quantity
      uses find_one_and_update with a $expr guard – single atomic operation).
  3.  Insert the claim document.
  4.  If step 3 fails, roll back the quantity reservation.

Completing a claim:
  1.  Update claim status to 'completed'.
  2.  Create an immutable rescue_record.
  3.  Update listing status to 'rescued' if fully claimed.

Cancelling a claim:
  1.  Update claim status to 'cancelled'.
  2.  Release reserved quantity back to the listing.
  3.  Revert listing to 'available' if it was 'reserved'.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pymongo.database import Database

from validators import validate_claim, validate_claim_transition
from repositories.claim_repo import (
    create_claim,
    get_claim_by_id,
    get_claims_for_listing,
    get_claims_for_user,
    get_claims_with_details,
    update_claim_status,
    get_claim_counts_by_status,
)
from repositories.listing_repo import (
    get_listing_by_id,
    increment_claimed_quantity,
    release_claimed_quantity,
    update_listing_status,
)
from repositories.rescue_repo import create_rescue_record


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
#  Claim food
# ─────────────────────────────────────────────────────────────────────────────

def claim_food(db: Database, form_data: dict) -> tuple[bool, str]:
    """
    Full claim workflow with atomic quantity reservation.

    form_data keys: listing_id, claimant_id, claimed_quantity, notes (optional)
    Returns (True, claim_id) or (False, error_message).
    """
    # 1. Fetch listing for validation context
    listing = get_listing_by_id(db, str(form_data.get("listing_id", "")))

    # 2. Application-level validation (includes listing status + deadline + qty checks)
    ok, errors = validate_claim(form_data, listing)
    if not ok:
        return False, "  •  " + "\n  •  ".join(errors)

    amount = float(form_data["claimed_quantity"])

    # 3. Atomically reserve quantity on the listing
    reserved_ok, reserve_msg = increment_claimed_quantity(
        db, str(form_data["listing_id"]), amount
    )
    if not reserved_ok:
        return False, reserve_msg

    # 4. Insert claim document
    claim_ok, claim_result = create_claim(db, form_data)
    if not claim_ok:
        # Roll back the reservation
        release_claimed_quantity(db, str(form_data["listing_id"]), amount)
        return False, f"Failed to record claim: {claim_result}"

    return True, claim_result  # claim_result is the new claim_id string


# ─────────────────────────────────────────────────────────────────────────────
#  Confirm claim
# ─────────────────────────────────────────────────────────────────────────────

def confirm_claim(db: Database, claim_id: str) -> tuple[bool, str]:
    """Move a claim from 'pending' → 'confirmed'."""
    claim = get_claim_by_id(db, claim_id)
    if not claim:
        return False, "Claim not found."
    ok, errors = validate_claim_transition(claim["status"], "confirmed")
    if not ok:
        return False, errors[0]
    return update_claim_status(db, claim_id, "confirmed")


# ─────────────────────────────────────────────────────────────────────────────
#  Complete claim → create rescue record
# ─────────────────────────────────────────────────────────────────────────────

def complete_claim(db: Database, claim_id: str) -> tuple[bool, str]:
    """
    Move claim to 'completed', create a rescue_record, and update listing
    status to 'rescued' if all quantity is now accounted for.
    """
    claim = get_claim_by_id(db, claim_id)
    if not claim:
        return False, "Claim not found."

    ok, errors = validate_claim_transition(claim["status"], "completed")
    if not ok:
        return False, errors[0]

    listing = get_listing_by_id(db, str(claim["listing_id"]))
    if not listing:
        return False, "Associated listing not found."

    # Update claim status
    status_ok, status_msg = update_claim_status(db, claim_id, "completed")
    if not status_ok:
        return False, status_msg

    # Create immutable rescue record
    rescue_data = {
        "claim_id":         str(claim["_id"]),
        "listing_id":       str(listing["_id"]),
        "donor_id":         str(listing["donor_id"]),
        "recipient_id":     str(claim["claimant_id"]),
        "rescued_quantity": float(claim["claimed_quantity"]),
        "unit":             listing["unit"],
        "category":         listing["category"],
        "food_title":       listing["title"],
        "pickup_location":  listing["pickup_location"],
        "rescued_at":       _now(),
    }
    rescue_ok, rescue_msg = create_rescue_record(db, rescue_data)
    if not rescue_ok:
        # Rescue record failed but claim is already marked completed.
        # Log and surface the error – do not silently ignore.
        return True, f"Claim completed but rescue record failed: {rescue_msg}"

    # If the listing is fully claimed, mark it rescued
    total = float(listing.get("quantity", 0))
    claimed = float(listing.get("claimed_quantity", 0))
    if claimed >= total and listing["status"] != "rescued":
        update_listing_status(db, str(listing["_id"]), "rescued")

    return True, rescue_msg  # rescue record id


# ─────────────────────────────────────────────────────────────────────────────
#  Cancel claim → release quantity
# ─────────────────────────────────────────────────────────────────────────────

def cancel_claim(db: Database, claim_id: str) -> tuple[bool, str]:
    """
    Cancel a claim and release its reserved quantity back to the listing.
    Only pending or confirmed claims can be cancelled.
    """
    claim = get_claim_by_id(db, claim_id)
    if not claim:
        return False, "Claim not found."

    ok, errors = validate_claim_transition(claim["status"], "cancelled")
    if not ok:
        return False, errors[0]

    # Update claim first
    status_ok, status_msg = update_claim_status(db, claim_id, "cancelled")
    if not status_ok:
        return False, status_msg

    # Release quantity back to listing
    amount = float(claim["claimed_quantity"])
    release_claimed_quantity(db, str(claim["listing_id"]), amount)

    return True, "Claim cancelled and quantity released."


# ─────────────────────────────────────────────────────────────────────────────
#  Read helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_claim(db: Database, claim_id: str) -> Optional[dict]:
    return get_claim_by_id(db, claim_id)


def fetch_listing_claims(db: Database, listing_id: str) -> list[dict]:
    return get_claims_for_listing(db, listing_id)


def fetch_user_claims(
    db: Database, user_id: str, status: Optional[str] = None
) -> list[dict]:
    return get_claims_for_user(db, user_id, status=status)


def fetch_all_claims_detailed(
    db: Database, claimant_id: Optional[str] = None
) -> list[dict]:
    return get_claims_with_details(db, claimant_id=claimant_id)


def claim_status_summary(db: Database) -> dict:
    return get_claim_counts_by_status(db)
