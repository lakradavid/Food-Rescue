"""
database.py
-----------
MongoDB connection management and one-time database setup.

Responsibilities:
  1. Provide a singleton MongoClient / database object.
  2. Create collections with JSON Schema validation rules.
  3. Create all required indexes.

Call `init_db()` once at application startup (app.py does this).
All other modules call `get_db()` to obtain the database handle.
"""

from __future__ import annotations

import logging
from typing import Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import CollectionInvalid, ConnectionFailure, OperationFailure

from config import (
    MONGO_URI,
    MONGO_DB_NAME,
    FOOD_CATEGORIES,
    QUANTITY_UNITS,
    LISTING_STATUSES,
    CLAIM_STATUSES,
    USER_ROLES,
)

logger = logging.getLogger(__name__)

# Module-level singleton – populated by init_db()
_client: Optional[MongoClient] = None
_db: Optional[Database] = None


# ─────────────────────────────────────────────────────────────────────────────
#  Connection helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_client() -> MongoClient:
    """Return the shared MongoClient, creating it on first call."""
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client


def get_db() -> Database:
    """Return the shared Database handle. Raises if init_db() was not called."""
    global _db
    if _db is None:
        _db = get_client()[MONGO_DB_NAME]
    return _db


def test_connection() -> bool:
    """Ping the server. Returns True on success, False on failure."""
    try:
        get_client().admin.command("ping")
        return True
    except ConnectionFailure as exc:
        logger.error("MongoDB connection failed: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  JSON Schema validators (applied at the MongoDB level)
# ─────────────────────────────────────────────────────────────────────────────

_USERS_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["name", "email", "role", "created_at"],
        "properties": {
            "name":       {"bsonType": "string",  "minLength": 2},
            "email":      {"bsonType": "string",  "pattern": "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"},
            "role":       {"bsonType": "string",  "enum": USER_ROLES},
            "phone":      {"bsonType": ["string", "null"]},
            "location":   {"bsonType": ["string", "null"]},
            "created_at": {"bsonType": "date"},
        },
    }
}

_FOOD_LISTINGS_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "title", "category", "quantity", "unit",
            "donor_id", "pickup_location", "status",
            "prepared_at", "pickup_deadline", "created_at",
        ],
        "properties": {
            "title":           {"bsonType": "string",  "minLength": 2},
            "category":        {"bsonType": "string",  "enum": FOOD_CATEGORIES},
            "quantity":        {"bsonType": ["int", "double"], "minimum": 0.01},
            "unit":            {"bsonType": "string",  "enum": QUANTITY_UNITS},
            "donor_id":        {"bsonType": "objectId"},
            "pickup_location": {"bsonType": "string",  "minLength": 2},
            "status":          {"bsonType": "string",  "enum": LISTING_STATUSES},
            "prepared_at":     {"bsonType": "date"},
            "pickup_deadline": {"bsonType": "date"},
            "created_at":      {"bsonType": "date"},
            "updated_at":      {"bsonType": ["date", "null"]},
            "allergens":       {"bsonType": ["array", "null"]},
            "description":     {"bsonType": ["string", "null"]},
            "claimed_quantity":{"bsonType": ["int", "double", "null"], "minimum": 0},
        },
    }
}

_CLAIMS_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "listing_id", "claimant_id", "claimed_quantity",
            "status", "created_at",
        ],
        "properties": {
            "listing_id":       {"bsonType": "objectId"},
            "claimant_id":      {"bsonType": "objectId"},
            "claimed_quantity": {"bsonType": ["int", "double"], "minimum": 0.01},
            "status":           {"bsonType": "string", "enum": CLAIM_STATUSES},
            "created_at":       {"bsonType": "date"},
            "updated_at":       {"bsonType": ["date", "null"]},
            "notes":            {"bsonType": ["string", "null"]},
        },
    }
}

_RESCUE_RECORDS_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "claim_id", "listing_id", "donor_id",
            "recipient_id", "rescued_quantity", "unit",
            "category", "pickup_location", "rescued_at",
        ],
        "properties": {
            "claim_id":         {"bsonType": "objectId"},
            "listing_id":       {"bsonType": "objectId"},
            "donor_id":         {"bsonType": "objectId"},
            "recipient_id":     {"bsonType": "objectId"},
            "rescued_quantity": {"bsonType": ["int", "double"], "minimum": 0.01},
            "unit":             {"bsonType": "string", "enum": QUANTITY_UNITS},
            "category":         {"bsonType": "string", "enum": FOOD_CATEGORIES},
            "pickup_location":  {"bsonType": "string"},
            "rescued_at":       {"bsonType": "date"},
        },
    }
}


# ─────────────────────────────────────────────────────────────────────────────
#  Collection + index setup
# ─────────────────────────────────────────────────────────────────────────────

def _create_collection_if_missing(db: Database, name: str, validator: dict) -> None:
    """Create collection with schema validator. Skip if already exists."""
    try:
        db.create_collection(name, validator=validator)
        logger.info("Created collection '%s'", name)
    except CollectionInvalid:
        # Collection exists – update the validator in case the schema changed
        try:
            db.command("collMod", name, validator=validator)
            logger.info("Updated validator on existing collection '%s'", name)
        except OperationFailure as exc:
            logger.warning("Could not update validator for '%s': %s", name, exc)


def _ensure_indexes(db: Database) -> None:
    """Create all required indexes (idempotent – safe to call multiple times)."""

    # users
    db.users.create_index([("email", ASCENDING)], unique=True, name="users_email_unique")
    db.users.create_index([("role", ASCENDING)], name="users_role")

    # food_listings
    db.food_listings.create_index([("status", ASCENDING)],          name="listings_status")
    db.food_listings.create_index([("category", ASCENDING)],        name="listings_category")
    db.food_listings.create_index([("pickup_location", ASCENDING)], name="listings_location")
    db.food_listings.create_index([("pickup_deadline", ASCENDING)], name="listings_deadline")
    db.food_listings.create_index([("donor_id", ASCENDING)],        name="listings_donor")
    db.food_listings.create_index(
        [("status", ASCENDING), ("pickup_deadline", ASCENDING)],
        name="listings_status_deadline",
    )

    # claims
    db.claims.create_index([("listing_id", ASCENDING)], name="claims_listing")
    db.claims.create_index([("claimant_id", ASCENDING)], name="claims_claimant")
    db.claims.create_index([("status", ASCENDING)],      name="claims_status")

    # rescue_records
    db.rescue_records.create_index([("donor_id", ASCENDING)],      name="rescue_donor")
    db.rescue_records.create_index([("recipient_id", ASCENDING)],  name="rescue_recipient")
    db.rescue_records.create_index([("rescued_at", DESCENDING)],   name="rescue_date")
    db.rescue_records.create_index([("category", ASCENDING)],      name="rescue_category")

    logger.info("All indexes ensured.")


def init_db() -> Database:
    """
    One-time startup routine:
      1. Verify connection.
      2. Create collections with validators.
      3. Ensure indexes.
    Returns the Database handle.
    """
    db = get_db()

    if not test_connection():
        raise ConnectionFailure(
            "Cannot reach MongoDB. Check MONGO_URI in your .env file."
        )

    _create_collection_if_missing(db, "users",          _USERS_SCHEMA)
    _create_collection_if_missing(db, "food_listings",  _FOOD_LISTINGS_SCHEMA)
    _create_collection_if_missing(db, "claims",         _CLAIMS_SCHEMA)
    _create_collection_if_missing(db, "rescue_records", _RESCUE_RECORDS_SCHEMA)

    _ensure_indexes(db)
    logger.info("Database initialised: %s", MONGO_DB_NAME)
    return db
