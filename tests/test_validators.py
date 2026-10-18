"""
tests/test_validators.py
------------------------
Unit tests for validators.py — no database required.

Tests every validation rule: required fields, formats, ranges,
status transitions, and claim quantity checks.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from validators import (
    validate_user,
    validate_food_listing,
    validate_claim,
    validate_claim_transition,
    validate_listing_transition,
)


def _now():
    return datetime.now(timezone.utc)


# ═════════════════════════════════════════════════════════════════════════════
#  User validation
# ═════════════════════════════════════════════════════════════════════════════

class TestValidateUser:

    def test_valid_user_passes(self):
        data = {"name": "Ravi Kumar", "email": "ravi@example.com", "role": "donor"}
        ok, errors = validate_user(data)
        assert ok is True
        assert errors == []

    def test_missing_name_fails(self):
        data = {"email": "ravi@example.com", "role": "donor"}
        ok, errors = validate_user(data)
        assert ok is False
        assert any("Name" in e for e in errors)

    def test_blank_name_fails(self):
        data = {"name": "  ", "email": "ravi@example.com", "role": "donor"}
        ok, errors = validate_user(data)
        assert ok is False

    def test_name_too_short_fails(self):
        data = {"name": "A", "email": "ravi@example.com", "role": "donor"}
        ok, errors = validate_user(data)
        assert ok is False

    def test_missing_email_fails(self):
        data = {"name": "Ravi Kumar", "role": "donor"}
        ok, errors = validate_user(data)
        assert ok is False
        assert any("Email" in e for e in errors)

    def test_invalid_email_format_fails(self):
        for bad in ["notanemail", "missing@", "@nodomain.com", "space @test.com"]:
            data = {"name": "Ravi", "email": bad, "role": "donor"}
            ok, errors = validate_user(data)
            assert ok is False, f"Expected fail for email '{bad}'"

    def test_invalid_role_fails(self):
        data = {"name": "Ravi", "email": "ravi@test.com", "role": "admin"}
        ok, errors = validate_user(data)
        assert ok is False
        assert any("Role" in e for e in errors)

    def test_valid_phone_passes(self):
        data = {"name": "Ravi", "email": "ravi@test.com", "role": "donor", "phone": "+91 98765 43210"}
        ok, errors = validate_user(data)
        assert ok is True

    def test_invalid_phone_fails(self):
        data = {"name": "Ravi", "email": "ravi@test.com", "role": "donor", "phone": "abc"}
        ok, errors = validate_user(data)
        assert ok is False

    def test_all_roles_accepted(self):
        for role in ("donor", "recipient", "volunteer"):
            data = {"name": "Test", "email": f"{role}@test.com", "role": role}
            ok, _ = validate_user(data)
            assert ok is True, f"Role '{role}' should be valid"


# ═════════════════════════════════════════════════════════════════════════════
#  Food listing validation
# ═════════════════════════════════════════════════════════════════════════════

class TestValidateFoodListing:

    def _base(self, **overrides):
        data = {
            "title":           "Dal Makhani",
            "category":        "Cooked Meal",
            "quantity":        5.0,
            "unit":            "kg",
            "donor_id":        "507f1f77bcf86cd799439011",
            "pickup_location": "LPU Block 32",
            "prepared_at":     _now() - timedelta(hours=1),
            "pickup_deadline": _now() + timedelta(hours=4),
        }
        data.update(overrides)
        return data

    def test_valid_listing_passes(self):
        ok, errors = validate_food_listing(self._base())
        assert ok is True, f"Unexpected errors: {errors}"

    def test_missing_title_fails(self):
        ok, errors = validate_food_listing(self._base(title=""))
        assert ok is False
        assert any("title" in e.lower() for e in errors)

    def test_invalid_category_fails(self):
        ok, errors = validate_food_listing(self._base(category="Pizza"))
        assert ok is False

    def test_zero_quantity_fails(self):
        ok, errors = validate_food_listing(self._base(quantity=0))
        assert ok is False

    def test_negative_quantity_fails(self):
        ok, errors = validate_food_listing(self._base(quantity=-1))
        assert ok is False

    def test_invalid_unit_fails(self):
        ok, errors = validate_food_listing(self._base(unit="tonnes"))
        assert ok is False

    def test_past_deadline_fails(self):
        ok, errors = validate_food_listing(
            self._base(pickup_deadline=_now() - timedelta(hours=1))
        )
        assert ok is False
        assert any("future" in e.lower() for e in errors)

    def test_deadline_before_prepared_fails(self):
        ok, errors = validate_food_listing(self._base(
            prepared_at=_now() + timedelta(hours=2),
            pickup_deadline=_now() + timedelta(hours=1),
        ))
        assert ok is False
        assert any("after" in e.lower() for e in errors)

    def test_missing_donor_id_fails(self):
        ok, errors = validate_food_listing(self._base(donor_id=""))
        assert ok is False

    def test_allergens_must_be_list(self):
        ok, errors = validate_food_listing(self._base(allergens="gluten"))
        assert ok is False

    def test_allergens_list_of_strings_passes(self):
        ok, errors = validate_food_listing(self._base(allergens=["gluten", "dairy"]))
        assert ok is True

    def test_description_too_long_fails(self):
        ok, errors = validate_food_listing(self._base(description="x" * 1001))
        assert ok is False


# ═════════════════════════════════════════════════════════════════════════════
#  Claim validation
# ═════════════════════════════════════════════════════════════════════════════

class TestValidateClaim:

    def _listing(self, **overrides):
        base = {
            "_id":              "abc123",
            "status":           "available",
            "quantity":         10.0,
            "claimed_quantity": 0.0,
            "unit":             "kg",
            "pickup_deadline":  _now() + timedelta(hours=4),
        }
        base.update(overrides)
        return base

    def test_valid_claim_passes(self):
        data    = {"listing_id": "l1", "claimant_id": "u1", "claimed_quantity": 3.0}
        listing = self._listing()
        ok, errors = validate_claim(data, listing)
        assert ok is True, f"Unexpected errors: {errors}"

    def test_missing_claimant_fails(self):
        data    = {"listing_id": "l1", "claimant_id": "", "claimed_quantity": 3.0}
        ok, errors = validate_claim(data, self._listing())
        assert ok is False

    def test_zero_quantity_fails(self):
        data = {"listing_id": "l1", "claimant_id": "u1", "claimed_quantity": 0}
        ok, errors = validate_claim(data, self._listing())
        assert ok is False

    def test_overclaim_fails(self):
        """Cannot claim more than available quantity."""
        data    = {"listing_id": "l1", "claimant_id": "u1", "claimed_quantity": 15.0}
        listing = self._listing(quantity=10.0, claimed_quantity=0.0)
        ok, errors = validate_claim(data, listing)
        assert ok is False
        assert any("available" in e.lower() for e in errors)

    def test_partial_claim_leaves_available(self):
        """Claiming 3 of 10 when 5 already claimed (5 available) → 3 ≤ 5, OK."""
        data    = {"listing_id": "l1", "claimant_id": "u1", "claimed_quantity": 3.0}
        listing = self._listing(quantity=10.0, claimed_quantity=5.0)
        ok, errors = validate_claim(data, listing)
        assert ok is True

    def test_exact_available_quantity_passes(self):
        data    = {"listing_id": "l1", "claimant_id": "u1", "claimed_quantity": 5.0}
        listing = self._listing(quantity=10.0, claimed_quantity=5.0)
        ok, errors = validate_claim(data, listing)
        assert ok is True

    def test_expired_listing_rejected(self):
        data    = {"listing_id": "l1", "claimant_id": "u1", "claimed_quantity": 2.0}
        listing = self._listing(
            pickup_deadline=_now() - timedelta(hours=1),
            status="available",
        )
        ok, errors = validate_claim(data, listing)
        assert ok is False
        assert any("deadline" in e.lower() for e in errors)

    def test_non_available_status_rejected(self):
        for bad_status in ("rescued", "expired", "reserved"):
            data    = {"listing_id": "l1", "claimant_id": "u1", "claimed_quantity": 2.0}
            listing = self._listing(status=bad_status)
            ok, errors = validate_claim(data, listing)
            assert ok is False, f"Status '{bad_status}' should not be claimable"

    def test_none_listing_fails(self):
        data = {"listing_id": "l1", "claimant_id": "u1", "claimed_quantity": 2.0}
        ok, errors = validate_claim(data, None)
        assert ok is False
        assert any("does not exist" in e.lower() for e in errors)


# ═════════════════════════════════════════════════════════════════════════════
#  Status transition validation
# ═════════════════════════════════════════════════════════════════════════════

class TestStatusTransitions:

    # Claim transitions
    def test_pending_to_confirmed_ok(self):
        ok, _ = validate_claim_transition("pending", "confirmed")
        assert ok is True

    def test_pending_to_cancelled_ok(self):
        ok, _ = validate_claim_transition("pending", "cancelled")
        assert ok is True

    def test_pending_to_completed_fails(self):
        ok, _ = validate_claim_transition("pending", "completed")
        assert ok is False

    def test_confirmed_to_completed_ok(self):
        ok, _ = validate_claim_transition("confirmed", "completed")
        assert ok is True

    def test_confirmed_to_cancelled_ok(self):
        ok, _ = validate_claim_transition("confirmed", "cancelled")
        assert ok is True

    def test_completed_is_terminal(self):
        for target in ("pending", "confirmed", "cancelled"):
            ok, _ = validate_claim_transition("completed", target)
            assert ok is False

    def test_cancelled_is_terminal(self):
        for target in ("pending", "confirmed", "completed"):
            ok, _ = validate_claim_transition("cancelled", target)
            assert ok is False

    # Listing transitions
    def test_available_to_reserved_ok(self):
        ok, _ = validate_listing_transition("available", "reserved")
        assert ok is True

    def test_available_to_expired_ok(self):
        ok, _ = validate_listing_transition("available", "expired")
        assert ok is True

    def test_available_to_rescued_fails(self):
        ok, _ = validate_listing_transition("available", "rescued")
        assert ok is False

    def test_rescued_is_terminal(self):
        for target in ("available", "reserved", "expired"):
            ok, _ = validate_listing_transition("rescued", target)
            assert ok is False

    def test_invalid_status_fails(self):
        ok, errors = validate_claim_transition("pending", "unknown_status")
        assert ok is False
        assert any("valid" in e.lower() for e in errors)
