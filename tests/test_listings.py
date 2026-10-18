"""
tests/test_listings.py
----------------------
Integration tests for food listing CRUD, expiry, and quantity management.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from conftest import make_donor, make_listing


def _now():
    return datetime.now(timezone.utc)


class TestCreateListing:

    def test_create_valid_listing(self, db):
        donor_id = make_donor(db)
        lid = make_listing(db, donor_id)
        assert len(lid) == 24

        doc = db.food_listings.find_one_by_id_str = None  # not used
        from repositories.listing_repo import get_listing_by_id
        listing = get_listing_by_id(db, lid)
        assert listing is not None
        assert listing["status"] == "available"
        assert listing["claimed_quantity"] == 0.0

    def test_past_deadline_rejected(self, db):
        from services.listing_service import add_listing
        donor_id = make_donor(db)
        ok, msg = add_listing(db, {
            "title":           "Stale Food",
            "category":        "Cooked Meal",
            "quantity":        5.0,
            "unit":            "kg",
            "donor_id":        donor_id,
            "pickup_location": "Somewhere",
            "prepared_at":     _now() - timedelta(hours=10),
            "pickup_deadline": _now() - timedelta(hours=2),  # past!
            "allergens":       [],
        })
        assert ok is False
        assert "future" in msg.lower()

    def test_zero_quantity_rejected(self, db):
        from services.listing_service import add_listing
        donor_id = make_donor(db)
        ok, msg = add_listing(db, {
            "title": "Empty Listing", "category": "Cooked Meal",
            "quantity": 0, "unit": "kg",
            "donor_id": donor_id,
            "pickup_location": "Test",
            "prepared_at": _now() - timedelta(hours=1),
            "pickup_deadline": _now() + timedelta(hours=4),
        })
        assert ok is False

    def test_invalid_category_rejected(self, db):
        from services.listing_service import add_listing
        donor_id = make_donor(db)
        ok, msg = add_listing(db, {
            "title": "Mystery Food", "category": "Alien Cuisine",
            "quantity": 5, "unit": "kg",
            "donor_id": donor_id,
            "pickup_location": "Mars",
            "prepared_at": _now() - timedelta(hours=1),
            "pickup_deadline": _now() + timedelta(hours=4),
        })
        assert ok is False


class TestReadListings:

    def test_fetch_active_excludes_expired(self, db):
        from services.listing_service import fetch_active_listings

        donor_id = make_donor(db)
        make_listing(db, donor_id, hours_until_deadline=6)    # active
        make_listing(db, donor_id, hours_until_deadline=12)   # active

        # Manually insert an expired listing (bypass service to set past deadline)
        db.food_listings.insert_one({
            "title": "Expired Food", "category": "Cooked Meal",
            "quantity": 5.0, "claimed_quantity": 0.0, "unit": "kg",
            "donor_id": __import__("bson").ObjectId(donor_id),
            "pickup_location": "Test", "status": "expired",
            "prepared_at": _now() - timedelta(days=2),
            "pickup_deadline": _now() - timedelta(days=1),
            "allergens": [], "created_at": _now(), "updated_at": None,
        })

        active = fetch_active_listings(db)
        assert len(active) == 2
        assert all(l["status"] == "available" for l in active)

    def test_fetch_donor_listings_returns_only_theirs(self, db):
        from services.listing_service import fetch_donor_listings

        d1 = make_donor(db, email="d1@test.com")
        d2 = make_donor(db, name="Donor 2", email="d2@test.com")

        make_listing(db, d1)
        make_listing(db, d1)
        make_listing(db, d2)

        d1_listings = fetch_donor_listings(db, d1)
        assert len(d1_listings) == 2
        assert all(str(l["donor_id"]) == d1 for l in d1_listings)

    def test_category_filter_works(self, db):
        from services.listing_service import fetch_active_listings, add_listing

        donor_id = make_donor(db)
        make_listing(db, donor_id)  # "Cooked Meal"

        add_listing(db, {
            "title": "Fresh Apples", "category": "Fruits & Vegetables",
            "quantity": 5, "unit": "kg", "donor_id": donor_id,
            "pickup_location": "Test",
            "prepared_at": _now() - timedelta(hours=1),
            "pickup_deadline": _now() + timedelta(hours=6),
        })

        meals  = fetch_active_listings(db, category="Cooked Meal")
        fruits = fetch_active_listings(db, category="Fruits & Vegetables")
        assert len(meals)  == 1
        assert len(fruits) == 1


class TestUpdateListing:

    def test_edit_own_available_listing(self, db):
        from services.listing_service import edit_listing
        from repositories.listing_repo import get_listing_by_id

        donor_id = make_donor(db)
        lid      = make_listing(db, donor_id)

        ok, msg = edit_listing(db, lid, {"title": "Updated Title"}, donor_id)
        assert ok is True

        updated = get_listing_by_id(db, lid)
        assert updated["title"] == "Updated Title"

    def test_cannot_edit_another_donors_listing(self, db):
        from services.listing_service import edit_listing

        d1 = make_donor(db, email="d1@test.com")
        d2 = make_donor(db, name="D2", email="d2@test.com")
        lid = make_listing(db, d1)

        ok, msg = edit_listing(db, lid, {"title": "Hijacked"}, d2)
        assert ok is False
        assert "own" in msg.lower()

    def test_cannot_edit_rescued_listing(self, db):
        from services.listing_service import edit_listing

        donor_id = make_donor(db)
        lid      = make_listing(db, donor_id, status="rescued")

        ok, msg = edit_listing(db, lid, {"title": "New Title"}, donor_id)
        assert ok is False


class TestDeleteListing:

    def test_delete_available_listing(self, db):
        from services.listing_service import remove_listing, fetch_listing

        donor_id = make_donor(db)
        lid      = make_listing(db, donor_id)

        ok, msg = remove_listing(db, lid, donor_id)
        assert ok is True
        assert fetch_listing(db, lid) is None

    def test_cannot_delete_rescued_listing(self, db):
        from services.listing_service import remove_listing

        donor_id = make_donor(db)
        lid      = make_listing(db, donor_id, status="rescued")

        ok, msg = remove_listing(db, lid, donor_id)
        assert ok is False


class TestExpiryRules:

    def test_sweep_marks_overdue_listings_expired(self, db):
        from services.listing_service import sweep_expired_listings

        donor_id = make_donor(db)

        # Insert a listing whose deadline is in the past (raw insert to bypass validator)
        db.food_listings.insert_one({
            "title": "Overdue", "category": "Cooked Meal",
            "quantity": 5.0, "claimed_quantity": 0.0, "unit": "kg",
            "donor_id": __import__("bson").ObjectId(donor_id),
            "pickup_location": "Test", "status": "available",
            "prepared_at": _now() - timedelta(days=2),
            "pickup_deadline": _now() - timedelta(hours=1),  # in the past
            "allergens": [], "created_at": _now(), "updated_at": None,
        })

        count = sweep_expired_listings(db)
        assert count == 1

        doc = db.food_listings.find_one({"title": "Overdue"})
        assert doc["status"] == "expired"
