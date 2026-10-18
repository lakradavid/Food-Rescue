"""
tests/test_analytics.py
-----------------------
Integration tests for all 6 aggregation pipelines.
Verifies that pipelines return the correct structure and values
given a known, controlled dataset inserted before each test.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from bson import ObjectId
from conftest import make_donor, make_recipient, make_listing


def _now():
    return datetime.now(timezone.utc)


def _insert_rescue_record(db, donor_id, recipient_id, qty, unit="kg",
                          category="Cooked Meal", location="Test Location",
                          days_ago=1):
    db.rescue_records.insert_one({
        "claim_id":         ObjectId(),
        "listing_id":       ObjectId(),
        "donor_id":         ObjectId(donor_id),
        "recipient_id":     ObjectId(recipient_id),
        "rescued_quantity": qty,
        "unit":             unit,
        "category":         category,
        "food_title":       "Test Food",
        "pickup_location":  location,
        "rescued_at":       _now() - timedelta(days=days_ago),
    })


def _insert_claim(db, listing_id, claimant_id, qty, status="completed"):
    db.claims.insert_one({
        "listing_id":       ObjectId(listing_id),
        "claimant_id":      ObjectId(claimant_id),
        "claimed_quantity": qty,
        "status":           status,
        "created_at":       _now() - timedelta(days=1),
        "updated_at":       _now(),
        "notes":            None,
    })


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 1 – Total Food Rescued
# ═════════════════════════════════════════════════════════════════════════════

class TestTotalFoodRescued:

    def test_empty_returns_empty_list(self, db):
        from analytics.pipelines import pipeline_total_food_rescued
        result = pipeline_total_food_rescued(db)
        assert result == []

    def test_sums_by_unit(self, db):
        from analytics.pipelines import pipeline_total_food_rescued
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)

        _insert_rescue_record(db, donor_id, recipient_id, qty=10.0, unit="kg")
        _insert_rescue_record(db, donor_id, recipient_id, qty=5.0,  unit="kg")
        _insert_rescue_record(db, donor_id, recipient_id, qty=20.0, unit="servings")

        result = pipeline_total_food_rescued(db)
        by_unit = {r["unit"]: r["total_rescued"] for r in result}

        assert by_unit["kg"] == 15.0
        assert by_unit["servings"] == 20.0

    def test_result_shape(self, db):
        from analytics.pipelines import pipeline_total_food_rescued
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        _insert_rescue_record(db, donor_id, recipient_id, qty=3.0)

        result = pipeline_total_food_rescued(db)
        assert len(result) == 1
        assert "unit"          in result[0]
        assert "total_rescued" in result[0]
        assert "rescue_count"  in result[0]


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 2 – Category Analysis
# ═════════════════════════════════════════════════════════════════════════════

class TestCategoryAnalysis:

    def test_groups_by_category_correctly(self, db):
        from analytics.pipelines import pipeline_category_analysis
        from services.listing_service import add_listing

        donor_id = make_donor(db)

        for i in range(3):
            add_listing(db, {
                "title": f"Meal {i}", "category": "Cooked Meal",
                "quantity": 5.0, "unit": "kg", "donor_id": donor_id,
                "pickup_location": "Test",
                "prepared_at": _now() - timedelta(hours=1),
                "pickup_deadline": _now() + timedelta(hours=6),
            })
        add_listing(db, {
            "title": "Bread", "category": "Bakery & Bread",
            "quantity": 2.0, "unit": "kg", "donor_id": donor_id,
            "pickup_location": "Test",
            "prepared_at": _now() - timedelta(hours=1),
            "pickup_deadline": _now() + timedelta(hours=6),
        })

        result = pipeline_category_analysis(db)
        by_cat = {r["category"]: r for r in result}

        assert by_cat["Cooked Meal"]["listing_count"] == 3
        assert by_cat["Cooked Meal"]["total_quantity"] == 15.0
        assert by_cat["Bakery & Bread"]["listing_count"] == 1

    def test_result_has_required_fields(self, db):
        from analytics.pipelines import pipeline_category_analysis
        donor_id = make_donor(db)
        make_listing(db, donor_id)

        result = pipeline_category_analysis(db)
        assert len(result) >= 1
        row = result[0]
        for field in ("category", "listing_count", "total_quantity",
                      "total_claimed", "remaining_quantity", "avg_quantity"):
            assert field in row, f"Missing field: {field}"


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 3 – Rescue Success Rate
# ═════════════════════════════════════════════════════════════════════════════

class TestRescueSuccessRate:

    def test_empty_returns_zeros(self, db):
        from analytics.pipelines import pipeline_rescue_success_rate
        result = pipeline_rescue_success_rate(db)
        assert result["total_claims"] == 0
        assert result["completion_pct"] == 0

    def test_completion_percentage_correct(self, db):
        from analytics.pipelines import pipeline_rescue_success_rate
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        lid = make_listing(db, donor_id, quantity=100.0)

        # 3 completed, 1 cancelled
        for _ in range(3):
            _insert_claim(db, lid, recipient_id, qty=5.0, status="completed")
        _insert_claim(db, lid, recipient_id, qty=5.0, status="cancelled")

        result = pipeline_rescue_success_rate(db)
        assert result["completed"]  == 3
        assert result["cancelled"]  == 1
        # 3 / (3+1) * 100 = 75%
        assert result["completion_pct"] == 75.0

    def test_all_completed_gives_100_percent(self, db):
        from analytics.pipelines import pipeline_rescue_success_rate
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        lid = make_listing(db, donor_id, quantity=100.0)

        for _ in range(5):
            _insert_claim(db, lid, recipient_id, qty=2.0, status="completed")

        result = pipeline_rescue_success_rate(db)
        assert result["completion_pct"] == 100.0


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 4 – Location Analysis
# ═════════════════════════════════════════════════════════════════════════════

class TestLocationAnalysis:

    def test_groups_listings_by_location(self, db):
        from analytics.pipelines import pipeline_location_analysis
        from services.listing_service import add_listing

        donor_id = make_donor(db)

        for _ in range(2):
            add_listing(db, {
                "title": "Food A", "category": "Cooked Meal",
                "quantity": 5.0, "unit": "kg", "donor_id": donor_id,
                "pickup_location": "Location Alpha",
                "prepared_at": _now() - timedelta(hours=1),
                "pickup_deadline": _now() + timedelta(hours=6),
            })
        add_listing(db, {
            "title": "Food B", "category": "Cooked Meal",
            "quantity": 3.0, "unit": "kg", "donor_id": donor_id,
            "pickup_location": "Location Beta",
            "prepared_at": _now() - timedelta(hours=1),
            "pickup_deadline": _now() + timedelta(hours=6),
        })

        result = pipeline_location_analysis(db)
        by_loc = {r["location"]: r for r in result}

        assert by_loc["Location Alpha"]["listing_count"] == 2
        assert by_loc["Location Beta"]["listing_count"]  == 1

    def test_rescues_counted_per_location(self, db):
        from analytics.pipelines import pipeline_location_analysis
        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)

        _insert_rescue_record(db, donor_id, recipient_id, qty=5.0,
                              location="Location Alpha")
        _insert_rescue_record(db, donor_id, recipient_id, qty=3.0,
                              location="Location Alpha")

        result = pipeline_location_analysis(db)
        by_loc = {r["location"]: r for r in result}

        assert by_loc["Location Alpha"]["rescue_count"] == 2


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 5 – Donor Performance
# ═════════════════════════════════════════════════════════════════════════════

class TestDonorPerformance:

    def test_ranks_donors_by_rescued_quantity(self, db):
        from analytics.pipelines import pipeline_donor_performance

        d1 = make_donor(db, email="d1@test.com")
        d2 = make_donor(db, name="D2", email="d2@test.com")
        r1 = make_recipient(db)

        _insert_rescue_record(db, d1, r1, qty=30.0)
        _insert_rescue_record(db, d2, r1, qty=10.0)

        result = pipeline_donor_performance(db)
        assert len(result) >= 2

        # Top donor should have higher total_rescued
        assert result[0]["total_rescued"] >= result[1]["total_rescued"]

    def test_result_has_required_fields(self, db):
        from analytics.pipelines import pipeline_donor_performance

        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        _insert_rescue_record(db, donor_id, recipient_id, qty=5.0)

        result = pipeline_donor_performance(db)
        assert len(result) == 1
        row = result[0]
        for field in ("donor_name", "total_rescued", "rescue_events", "categories"):
            assert field in row, f"Missing field: {field}"


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 6 – Rescue Trends
# ═════════════════════════════════════════════════════════════════════════════

class TestRescueTrends:

    def test_empty_returns_empty_list(self, db):
        from analytics.pipelines import pipeline_rescue_trends
        assert pipeline_rescue_trends(db, group_by="day") == []
        assert pipeline_rescue_trends(db, group_by="month") == []

    def test_day_grouping_correct(self, db):
        from analytics.pipelines import pipeline_rescue_trends

        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)

        # Two rescues 5 days ago, one rescue 3 days ago
        _insert_rescue_record(db, donor_id, recipient_id, qty=4.0, days_ago=5)
        _insert_rescue_record(db, donor_id, recipient_id, qty=6.0, days_ago=5)
        _insert_rescue_record(db, donor_id, recipient_id, qty=3.0, days_ago=3)

        result = pipeline_rescue_trends(db, group_by="day")
        assert len(result) == 2   # two distinct days

        # Chronological order
        assert result[0]["period"] < result[1]["period"]

        # The earlier day should have 2 rescues totalling 10 kg
        assert result[0]["rescue_count"]  == 2
        assert result[0]["total_rescued"] == 10.0

    def test_month_grouping_correct(self, db):
        from analytics.pipelines import pipeline_rescue_trends

        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)

        # Rescue this month and last month
        _insert_rescue_record(db, donor_id, recipient_id, qty=5.0,  days_ago=0)
        _insert_rescue_record(db, donor_id, recipient_id, qty=5.0,  days_ago=35)

        result = pipeline_rescue_trends(db, group_by="month")
        # Should have at most 2 distinct months
        assert 1 <= len(result) <= 2

    def test_result_shape(self, db):
        from analytics.pipelines import pipeline_rescue_trends

        donor_id     = make_donor(db)
        recipient_id = make_recipient(db)
        _insert_rescue_record(db, donor_id, recipient_id, qty=2.0)

        result = pipeline_rescue_trends(db, group_by="day")
        assert len(result) == 1
        row = result[0]
        assert "period"       in row
        assert "rescue_count" in row
        assert "total_rescued" in row


# ═════════════════════════════════════════════════════════════════════════════
#  Dashboard summary
# ═════════════════════════════════════════════════════════════════════════════

class TestDashboardSummary:

    def test_summary_returns_all_keys(self, db):
        from analytics.pipelines import get_dashboard_summary
        summary = get_dashboard_summary(db)

        expected_keys = [
            "active_listings", "expired_listings", "total_listings",
            "total_rescued_kg", "estimated_meals",
            "completed_rescues", "pending_claims", "cancelled_claims",
            "completion_pct", "total_users", "rescued_totals",
        ]
        for key in expected_keys:
            assert key in summary, f"Missing key in dashboard summary: {key}"

    def test_summary_counts_are_non_negative(self, db):
        from analytics.pipelines import get_dashboard_summary
        summary = get_dashboard_summary(db)
        numeric_keys = [
            "active_listings", "expired_listings", "total_listings",
            "total_rescued_kg", "completed_rescues", "pending_claims",
        ]
        for key in numeric_keys:
            assert summary[key] >= 0, f"Negative value for '{key}': {summary[key]}"
