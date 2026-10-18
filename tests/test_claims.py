"""
tests/test_claims.py
--------------------
Integration tests for the full claim lifecycle, including:
  - Valid claims
  - Over-claim prevention
  - Expired listing rejection
  - Status transitions (confirm, complete, cancel)
  - Rescue record creation on completion
  - Quantity release on cancellation
  - Correct rescue totals (cancelled claims must NOT be counted)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from conftest import make_donor, make_recipient, make_listing


def _now():
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _claim(db, listing_id, claimant_id, qty=3.0):
    from services.claim_service import claim_food
    return claim_food(db, {
        "listing_id":       listing_id,
        "claimant_id":      claimant_id,
        "claimed_quantity": qty,
    })


# ═════════════════════════════════════════════════════════════════════════════
#  Claim creation
# ═════════════════════════════════════════════════════════════════════════════

class TestClaimCreation:

    def test_valid_claim_succeeds(self, db):
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        lid          = make_listing(db, donor_id, quantity=10.0)

        ok, claim_id = _claim(db, lid, recipient_id, qty=4.0)
        assert ok is True
        assert len(claim_id) == 24

    def test_claimed_quantity_reserved_on_listing(self, db):
        """After a claim, claimed_quantity on the listing must increase."""
        from repositories.listing_repo import get_listing_by_id
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        lid          = make_listing(db, donor_id, quantity=10.0)

        _claim(db, lid, recipient_id, qty=4.0)

        listing = get_listing_by_id(db, lid)
        assert listing["claimed_quantity"] == 4.0
        assert listing["status"] == "reserved"

    def test_cannot_claim_more_than_available(self, db):
        """Over-claim must be rejected at the service layer."""
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        lid          = make_listing(db, donor_id, quantity=5.0)

        ok, msg = _claim(db, lid, recipient_id, qty=10.0)
        assert ok is False
        assert "available" in msg.lower() or "claim" in msg.lower()

    def test_two_claims_within_available_stock(self, db):
        """Two different recipients claiming parts of the same listing, both valid."""
        donor_id = make_donor(db)
        r1       = make_recipient(db, email="r1@test.com")
        r2       = make_recipient(db, name="Recipient 2", email="r2@test.com")
        lid      = make_listing(db, donor_id, quantity=10.0)

        ok1, _ = _claim(db, lid, r1, qty=4.0)
        ok2, _ = _claim(db, lid, r2, qty=4.0)
        assert ok1 is True
        assert ok2 is True

    def test_combined_claims_cannot_exceed_total(self, db):
        """3 + 3 + 5 against a 10 unit listing: third claim must fail."""
        donor_id = make_donor(db)
        r1 = make_recipient(db, email="r1@test.com")
        r2 = make_recipient(db, name="R2", email="r2@test.com")
        r3 = make_recipient(db, name="R3", email="r3@test.com")
        lid = make_listing(db, donor_id, quantity=10.0)

        _claim(db, lid, r1, qty=3.0)
        _claim(db, lid, r2, qty=3.0)
        ok3, msg = _claim(db, lid, r3, qty=5.0)  # only 4 remaining
        assert ok3 is False

    def test_claim_on_expired_listing_rejected(self, db):
        """A listing whose deadline has passed must not be claimable."""
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)

        # Raw insert with past deadline (bypasses validator that would block creation)
        from bson import ObjectId
        expired_id = db.food_listings.insert_one({
            "title": "Expired", "category": "Cooked Meal",
            "quantity": 5.0, "claimed_quantity": 0.0, "unit": "kg",
            "donor_id": ObjectId(donor_id),
            "pickup_location": "Test", "status": "available",
            "prepared_at": _now() - timedelta(days=2),
            "pickup_deadline": _now() - timedelta(hours=1),
            "allergens": [], "created_at": _now(), "updated_at": None,
        }).inserted_id

        ok, msg = _claim(db, str(expired_id), recipient_id, qty=2.0)
        assert ok is False
        assert "deadline" in msg.lower()

    def test_claim_on_rescued_listing_rejected(self, db):
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        lid          = make_listing(db, donor_id, status="rescued")

        ok, msg = _claim(db, lid, recipient_id, qty=2.0)
        assert ok is False


# ═════════════════════════════════════════════════════════════════════════════
#  Claim lifecycle
# ═════════════════════════════════════════════════════════════════════════════

class TestClaimLifecycle:

    def _setup(self, db):
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        lid          = make_listing(db, donor_id, quantity=10.0)
        ok, claim_id = _claim(db, lid, recipient_id, qty=4.0)
        assert ok, "Claim setup failed"
        return lid, claim_id

    def test_confirm_pending_claim(self, db):
        from services.claim_service import confirm_claim
        from repositories.claim_repo import get_claim_by_id

        lid, claim_id = self._setup(db)
        ok, msg = confirm_claim(db, claim_id)
        assert ok is True

        claim = get_claim_by_id(db, claim_id)
        assert claim["status"] == "confirmed"

    def test_complete_confirmed_claim_creates_rescue_record(self, db):
        from services.claim_service import confirm_claim, complete_claim

        lid, claim_id = self._setup(db)
        confirm_claim(db, claim_id)
        ok, rescue_id = complete_claim(db, claim_id)
        assert ok is True

        # Rescue record must exist
        from repositories.rescue_repo import get_rescue_record_by_id
        record = get_rescue_record_by_id(db, rescue_id)
        assert record is not None
        assert record["rescued_quantity"] == 4.0

    def test_complete_claim_updates_claim_status(self, db):
        from services.claim_service import confirm_claim, complete_claim
        from repositories.claim_repo import get_claim_by_id

        lid, claim_id = self._setup(db)
        confirm_claim(db, claim_id)
        complete_claim(db, claim_id)

        claim = get_claim_by_id(db, claim_id)
        assert claim["status"] == "completed"

    def test_cancel_pending_claim_releases_quantity(self, db):
        from services.claim_service import cancel_claim
        from repositories.listing_repo import get_listing_by_id

        lid, claim_id = self._setup(db)

        # Listing shows 4 reserved
        before = get_listing_by_id(db, lid)
        assert before["claimed_quantity"] == 4.0

        ok, msg = cancel_claim(db, claim_id)
        assert ok is True

        after = get_listing_by_id(db, lid)
        assert after["claimed_quantity"] == 0.0
        assert after["status"] == "available"

    def test_cancel_confirmed_claim_releases_quantity(self, db):
        from services.claim_service import confirm_claim, cancel_claim
        from repositories.listing_repo import get_listing_by_id

        lid, claim_id = self._setup(db)
        confirm_claim(db, claim_id)
        ok, msg = cancel_claim(db, claim_id)
        assert ok is True

        listing = get_listing_by_id(db, lid)
        assert listing["claimed_quantity"] == 0.0

    def test_cannot_cancel_completed_claim(self, db):
        from services.claim_service import confirm_claim, complete_claim, cancel_claim

        lid, claim_id = self._setup(db)
        confirm_claim(db, claim_id)
        complete_claim(db, claim_id)

        ok, msg = cancel_claim(db, claim_id)
        assert ok is False
        assert "terminal" in msg.lower() or "cannot" in msg.lower()

    def test_cannot_complete_pending_claim_directly(self, db):
        """Must go pending → confirmed → completed; skipping step must fail."""
        from services.claim_service import complete_claim

        lid, claim_id = self._setup(db)
        ok, msg = complete_claim(db, claim_id)  # still 'pending'
        assert ok is False

    def test_double_claim_prevention(self, db):
        """
        A user should not be able to claim more than available even if
        two requests arrive nearly simultaneously (atomic guard in repo).
        """
        donor_id = make_donor(db)
        r1 = make_recipient(db, email="r1@test.com")
        lid = make_listing(db, donor_id, quantity=5.0)

        ok1, _ = _claim(db, lid, r1, qty=5.0)   # claims all 5
        ok2, _ = _claim(db, lid, r1, qty=1.0)   # nothing left
        assert ok1 is True
        assert ok2 is False


# ═════════════════════════════════════════════════════════════════════════════
#  Rescue totals accuracy
# ═════════════════════════════════════════════════════════════════════════════

class TestRescueTotals:

    def test_cancelled_claims_not_counted_in_rescue_total(self, db):
        """
        Critical business rule: only COMPLETED claims create rescue records.
        Cancelled claims must contribute zero to the rescued total.
        """
        from services.claim_service import cancel_claim
        from repositories.rescue_repo import get_total_rescued_quantity

        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        lid          = make_listing(db, donor_id, quantity=10.0)

        ok, claim_id = _claim(db, lid, recipient_id, qty=5.0)
        assert ok

        cancel_claim(db, claim_id)

        totals = get_total_rescued_quantity(db)
        # No completed rescues → total should be zero (or empty list)
        total_kg = sum(r["total_rescued"] for r in totals if r["unit"] == "kg")
        assert total_kg == 0.0

    def test_completed_claims_appear_in_rescue_total(self, db):
        from services.claim_service import confirm_claim, complete_claim
        from repositories.rescue_repo import get_total_rescued_quantity

        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        lid          = make_listing(db, donor_id, quantity=10.0)

        _, claim_id = _claim(db, lid, recipient_id, qty=6.0)
        confirm_claim(db, claim_id)
        complete_claim(db, claim_id)

        totals = get_total_rescued_quantity(db)
        total_kg = sum(r["total_rescued"] for r in totals if r["unit"] == "kg")
        assert total_kg == 6.0
