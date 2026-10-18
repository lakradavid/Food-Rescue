"""
tests/test_matching.py
----------------------
Unit/integration tests for the smart matching service.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from bson import ObjectId
from conftest import make_donor, make_listing


def _now():
    return datetime.now(timezone.utc)


def _add_listing(db, donor_id, category, location, hours_left, qty=10.0):
    from services.listing_service import add_listing
    ok, lid = add_listing(db, {
        "title":           f"Food at {location}",
        "category":        category,
        "quantity":        qty,
        "unit":            "kg",
        "donor_id":        donor_id,
        "pickup_location": location,
        "prepared_at":     _now() - timedelta(hours=1),
        "pickup_deadline": _now() + timedelta(hours=hours_left),
    })
    assert ok, lid
    return lid


class TestSmartMatching:

    def test_returns_empty_when_no_listings(self, db):
        from services.matching_service import get_matched_listings
        result = get_matched_listings(db)
        assert result == []

    def test_category_match_scores_higher(self, db):
        from services.matching_service import get_matched_listings

        donor_id = make_donor(db)
        _add_listing(db, donor_id, "Cooked Meal",       "Test City", hours_left=8)
        _add_listing(db, donor_id, "Bakery & Bread",    "Test City", hours_left=8)

        results = get_matched_listings(
            db, preferred_category="Cooked Meal", top_n=10
        )
        assert len(results) >= 1
        # Top result must be the category-matched one
        assert results[0]["category"] == "Cooked Meal"

    def test_location_match_scores_higher(self, db):
        from services.matching_service import get_matched_listings

        donor_id = make_donor(db)
        _add_listing(db, donor_id, "Cooked Meal", "LPU Campus",      hours_left=8)
        _add_listing(db, donor_id, "Cooked Meal", "Faraway City",    hours_left=8)

        results = get_matched_listings(
            db, preferred_location="LPU", top_n=10
        )
        assert results[0]["pickup_location"] == "LPU Campus"

    def test_urgent_listings_ranked_highly(self, db):
        from services.matching_service import get_matched_listings

        donor_id = make_donor(db)
        _add_listing(db, donor_id, "Cooked Meal", "Test", hours_left=24)   # not urgent
        _add_listing(db, donor_id, "Cooked Meal", "Test", hours_left=1)    # very urgent

        # No preferences → urgency is the main differentiator
        results = get_matched_listings(db, top_n=10)
        assert results[0]["hours_left"] < results[-1]["hours_left"]

    def test_result_has_required_keys(self, db):
        from services.matching_service import get_matched_listings
        donor_id = make_donor(db)
        _add_listing(db, donor_id, "Cooked Meal", "Test", hours_left=6)

        results = get_matched_listings(db, top_n=5)
        assert len(results) >= 1
        for key in ("match_score", "hours_left", "available_qty", "explanation"):
            assert key in results[0], f"Missing key: {key}"

    def test_top_n_limits_results(self, db):
        from services.matching_service import get_matched_listings
        donor_id = make_donor(db)
        for i in range(8):
            _add_listing(db, donor_id, "Cooked Meal", f"Loc {i}", hours_left=6)

        results = get_matched_listings(db, top_n=3)
        assert len(results) == 3

    def test_fully_claimed_listings_excluded(self, db):
        from services.matching_service import get_matched_listings
        from repositories.listing_repo import get_listing_by_id

        donor_id = make_donor(db)
        lid = _add_listing(db, donor_id, "Cooked Meal", "Test", hours_left=6, qty=5.0)

        # Manually set claimed_quantity == quantity (fully claimed)
        db.food_listings.update_one(
            {"_id": ObjectId(lid)},
            {"$set": {"claimed_quantity": 5.0}},
        )

        results = get_matched_listings(db, top_n=10)
        assert all(r["available_qty"] > 0 for r in results)

    def test_scores_in_range_0_to_100(self, db):
        from services.matching_service import get_matched_listings
        donor_id = make_donor(db)
        _add_listing(db, donor_id, "Cooked Meal", "Test", hours_left=4)

        results = get_matched_listings(db, preferred_category="Cooked Meal",
                                       preferred_location="Test")
        for r in results:
            assert 0 <= r["match_score"] <= 100

    def test_urgency_alerts_threshold(self, db):
        from services.matching_service import get_urgency_alerts

        donor_id = make_donor(db)
        _add_listing(db, donor_id, "Cooked Meal", "Test", hours_left=1)    # alert
        _add_listing(db, donor_id, "Cooked Meal", "Test", hours_left=10)   # no alert

        alerts = get_urgency_alerts(db, hours_threshold=3.0)
        assert len(alerts) == 1
        assert alerts[0]["hours_left"] <= 3.0
