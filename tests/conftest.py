"""
tests/conftest.py
-----------------
Pytest fixtures shared across all test modules.

Uses a dedicated test database (foodrescue_test) so tests never
touch real data. Each test function gets a freshly wiped database
via the `db` fixture — fully isolated.

Run all tests from the foodrescue/ directory:
    pytest tests/ -v
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone, timedelta

import pytest
from pymongo import MongoClient

# Make project root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import MONGO_URI


TEST_DB_NAME = "foodrescue_test"


@pytest.fixture(scope="session")
def mongo_client():
    """One MongoClient for the entire test session."""
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    yield client
    client.close()


@pytest.fixture()
def db(mongo_client):
    """
    Fresh test database for each test function.
    Drops all collections before and after the test.
    """
    test_db = mongo_client[TEST_DB_NAME]

    # Clean slate before test
    for coll in ["users", "food_listings", "claims", "rescue_records"]:
        test_db[coll].drop()

    # Import init_db to create collections + indexes on the test DB
    import database as db_module
    original_db = db_module._db
    db_module._db = test_db          # point singleton at test DB
    db_module.init_db()              # create collections + indexes

    yield test_db

    # Teardown: clean up + restore
    for coll in ["users", "food_listings", "claims", "rescue_records"]:
        test_db[coll].drop()
    db_module._db = original_db      # restore original DB handle


# ─────────────────────────────────────────────────────────────────────────────
#  Reusable factory helpers (used in multiple test modules)
# ─────────────────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def make_donor(db, name="Test Donor", email="donor@test.com"):
    """Insert a minimal donor and return their _id string."""
    from services.user_service import register_user
    ok, uid = register_user(db, {
        "name":     name,
        "email":    email,
        "role":     "donor",
        "password": "test1234",
        "phone":    "+91 99000 00001",
        "location": "Test Location",
    })
    assert ok, f"make_donor failed: {uid}"
    return uid


def make_recipient(db, name="Test Recipient", email="recipient@test.com"):
    """Insert a minimal recipient and return their _id string."""
    from services.user_service import register_user
    ok, uid = register_user(db, {
        "name":     name,
        "email":    email,
        "role":     "recipient",
        "password": "test1234",
    })
    assert ok, f"make_recipient failed: {uid}"
    return uid


def make_listing(db, donor_id, *, hours_until_deadline=6, quantity=10.0, status=None):
    """Insert a minimal available listing and return its _id string."""
    from services.listing_service import add_listing
    from repositories.listing_repo import update_listing_status

    ok, lid = add_listing(db, {
        "title":           "Test Food Item",
        "category":        "Cooked Meal",
        "description":     "Test description",
        "quantity":        quantity,
        "unit":            "kg",
        "donor_id":        donor_id,
        "pickup_location": "Test Location",
        "prepared_at":     _now() - timedelta(hours=1),
        "pickup_deadline": _now() + timedelta(hours=hours_until_deadline),
        "allergens":       [],
    })
    assert ok, f"make_listing failed: {lid}"

    if status and status != "available":
        update_listing_status(db, lid, status)

    return lid
