"""
repositories/rescue_repo.py
---------------------------
All direct MongoDB operations for the `rescue_records` collection.

A rescue record is created when a claim reaches 'completed' status.
It is a denormalised snapshot capturing:
  - Who donated (donor_id, pickup_location)
  - Who received (recipient_id)
  - What food (category, title)
  - How much was rescued (rescued_quantity, unit)
  - When it happened (rescued_at)

Why denormalise here?
  Analytics pipelines on rescue data aggregate across many records over
  time.  If the original listing or claim is ever deleted, we still want
  accurate historical impact metrics.  The rescue record is an immutable
  audit trail — a write-once, read-many document.

The trade-off: we store some data redundantly (category, location, unit).
For an academic project at this scale, this is the right approach for
reliable analytics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from pymongo.database import Database
from pymongo.errors import PyMongoError


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
#  Create
# ─────────────────────────────────────────────────────────────────────────────

def create_rescue_record(db: Database, data: dict) -> tuple[bool, str]:
    """
    Insert an immutable rescue record.
    Called by the claim service when a claim is completed.
    """
    doc = {
        "claim_id":         ObjectId(str(data["claim_id"])),
        "listing_id":       ObjectId(str(data["listing_id"])),
        "donor_id":         ObjectId(str(data["donor_id"])),
        "recipient_id":     ObjectId(str(data["recipient_id"])),
        "rescued_quantity": float(data["rescued_quantity"]),
        "unit":             data["unit"],
        "category":         data["category"],
        "food_title":       data.get("food_title", "Unknown"),
        "pickup_location":  data["pickup_location"],
        "rescued_at":       data.get("rescued_at", _now()),
    }
    try:
        result = db.rescue_records.insert_one(doc)
        return True, str(result.inserted_id)
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
#  Read
# ─────────────────────────────────────────────────────────────────────────────

def get_rescue_record_by_id(db: Database, record_id: str) -> Optional[dict]:
    try:
        return db.rescue_records.find_one({"_id": ObjectId(record_id)})
    except Exception:
        return None


def get_all_rescue_records(
    db: Database,
    donor_id: Optional[str] = None,
    recipient_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Fetch rescue records with optional filters, most recent first."""
    query: dict = {}
    if donor_id:
        query["donor_id"] = ObjectId(donor_id)
    if recipient_id:
        query["recipient_id"] = ObjectId(recipient_id)
    if category:
        query["category"] = category
    return list(db.rescue_records.find(query).sort("rescued_at", -1).limit(limit))


def get_total_rescued_quantity(db: Database) -> dict:
    """
    Aggregate total rescued quantity per unit.
    Returns a list of {unit, total} dicts.
    """
    pipeline = [
        {
            "$group": {
                "_id": "$unit",
                "total_rescued": {"$sum": "$rescued_quantity"},
                "rescue_count":  {"$sum": 1},
            }
        },
        {"$sort": {"total_rescued": -1}},
    ]
    return list(db.rescue_records.aggregate(pipeline))


def get_recent_rescues(db: Database, limit: int = 10) -> list[dict]:
    """Return the most recent rescue records with donor/recipient names via $lookup."""
    pipeline = [
        {"$sort": {"rescued_at": -1}},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "users",
                "localField": "donor_id",
                "foreignField": "_id",
                "as": "donor",
            }
        },
        {"$unwind": {"path": "$donor", "preserveNullAndEmptyArrays": True}},
        {
            "$lookup": {
                "from": "users",
                "localField": "recipient_id",
                "foreignField": "_id",
                "as": "recipient",
            }
        },
        {"$unwind": {"path": "$recipient", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "food_title": 1,
                "category": 1,
                "rescued_quantity": 1,
                "unit": 1,
                "pickup_location": 1,
                "rescued_at": 1,
                "donor_name":     "$donor.name",
                "recipient_name": "$recipient.name",
            }
        },
    ]
    return list(db.rescue_records.aggregate(pipeline))
