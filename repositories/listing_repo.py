"""
repositories/listing_repo.py
-----------------------------
All direct MongoDB operations for the `food_listings` collection.

Document structure (key fields):
  _id              : ObjectId  – primary key
  title            : str       – food name/title
  category         : str       – one of FOOD_CATEGORIES
  description      : str|None
  quantity         : float     – original total quantity listed
  claimed_quantity : float     – running total of active claims
  unit             : str       – one of QUANTITY_UNITS
  donor_id         : ObjectId  – references users._id
  pickup_location  : str
  status           : str       – available | reserved | rescued | expired
  prepared_at      : datetime
  pickup_deadline  : datetime
  allergens        : list[str] | None
  created_at       : datetime
  updated_at       : datetime | None

Embedding vs referencing:
  The donor is referenced (ObjectId) rather than embedded. Donor details
  change infrequently but could change; referencing means one authoritative
  copy. The trade-off is a $lookup when we want to display donor names
  alongside listings.  For a read-heavy public browse page this is fine.
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

def create_listing(db: Database, data: dict) -> tuple[bool, str]:
    """
    Insert a new food listing.
    claimed_quantity starts at 0; status starts as 'available'.
    """
    doc = {
        "title":            data["title"].strip(),
        "category":         data["category"],
        "description":      data.get("description", "").strip() or None,
        "quantity":         float(data["quantity"]),
        "claimed_quantity": 0.0,
        "unit":             data["unit"],
        "donor_id":         ObjectId(str(data["donor_id"])),
        "pickup_location":  data["pickup_location"].strip(),
        "status":           "available",
        "prepared_at":      data["prepared_at"],
        "pickup_deadline":  data["pickup_deadline"],
        "allergens":        data.get("allergens") or [],
        "created_at":       _now(),
        "updated_at":       None,
    }
    try:
        result = db.food_listings.insert_one(doc)
        return True, str(result.inserted_id)
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
#  Read
# ─────────────────────────────────────────────────────────────────────────────

def get_listing_by_id(db: Database, listing_id: str) -> Optional[dict]:
    try:
        return db.food_listings.find_one({"_id": ObjectId(listing_id)})
    except Exception:
        return None


def get_listings(
    db: Database,
    status: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    donor_id: Optional[str] = None,
    only_active: bool = False,
    limit: int = 100,
    skip: int = 0,
) -> list[dict]:
    """
    Flexible query for listings.

    only_active=True  → status='available' AND deadline in the future.
    Other filters are ANDed together.
    """
    query: dict = {}

    if only_active:
        query["status"] = "available"
        query["pickup_deadline"] = {"$gt": _now()}
    elif status:
        query["status"] = status

    if category:
        query["category"] = category

    if location:
        # Case-insensitive partial match on pickup_location
        query["pickup_location"] = {"$regex": location, "$options": "i"}

    if donor_id:
        try:
            query["donor_id"] = ObjectId(donor_id)
        except Exception:
            pass

    return list(
        db.food_listings.find(query)
        .sort("pickup_deadline", 1)   # earliest deadline first
        .skip(skip)
        .limit(limit)
    )


def get_listings_with_donor(db: Database, query_filter: dict = None, limit: int = 50) -> list[dict]:
    """
    Return listings joined with donor name via $lookup.
    Useful for display pages where we need the donor's name.
    """
    pipeline = [
        {"$match": query_filter or {}},
        {"$sort": {"pickup_deadline": 1}},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "users",
                "localField": "donor_id",
                "foreignField": "_id",
                "as": "donor",
            }
        },
        # $unwind with preserveNullAndEmptyArrays so listings without a
        # matched donor still appear (data integrity issue, not a crash).
        {"$unwind": {"path": "$donor", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "title": 1, "category": 1, "description": 1,
                "quantity": 1, "claimed_quantity": 1, "unit": 1,
                "pickup_location": 1, "status": 1,
                "prepared_at": 1, "pickup_deadline": 1,
                "allergens": 1, "created_at": 1,
                "donor_name":     "$donor.name",
                "donor_location": "$donor.location",
            }
        },
    ]
    return list(db.food_listings.aggregate(pipeline))


# ─────────────────────────────────────────────────────────────────────────────
#  Update
# ─────────────────────────────────────────────────────────────────────────────

def update_listing(db: Database, listing_id: str, updates: dict) -> tuple[bool, str]:
    """
    Update editable listing fields.
    Quantity, status, and claimed_quantity have dedicated functions
    to enforce business rules.
    """
    editable = {"title", "description", "category", "unit", "pickup_location",
                "prepared_at", "pickup_deadline", "allergens"}
    safe = {k: v for k, v in updates.items() if k in editable}
    if not safe:
        return False, "No valid fields to update."
    safe["updated_at"] = _now()
    try:
        result = db.food_listings.update_one(
            {"_id": ObjectId(listing_id)},
            {"$set": safe},
        )
        if result.matched_count == 0:
            return False, "Listing not found."
        return True, "Listing updated."
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


def update_listing_status(db: Database, listing_id: str, new_status: str) -> tuple[bool, str]:
    """Update only the status field of a listing."""
    try:
        result = db.food_listings.update_one(
            {"_id": ObjectId(listing_id)},
            {"$set": {"status": new_status, "updated_at": _now()}},
        )
        if result.matched_count == 0:
            return False, "Listing not found."
        return True, f"Status updated to '{new_status}'."
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


def increment_claimed_quantity(
    db: Database, listing_id: str, amount: float
) -> tuple[bool, str]:
    """
    Atomically increment claimed_quantity using $inc.
    Also sets status to 'reserved' once any quantity is claimed,
    and to 'rescued' when fully claimed.

    Using findOneAndUpdate ensures the read-modify-write is atomic at
    the document level (MongoDB's document-level atomicity guarantee).
    """
    try:
        doc = db.food_listings.find_one_and_update(
            {
                "_id": ObjectId(listing_id),
                "status": "available",
                # Guard: ensure we don't over-claim
                "$expr": {
                    "$lte": [
                        {"$add": ["$claimed_quantity", amount]},
                        "$quantity",
                    ]
                },
            },
            {
                "$inc": {"claimed_quantity": amount},
                "$set": {"status": "reserved", "updated_at": _now()},
            },
            return_document=True,
        )
        if doc is None:
            return False, "Claim failed: listing is no longer available or quantity exceeded."

        # If fully claimed, mark as rescued
        if doc["claimed_quantity"] >= doc["quantity"]:
            db.food_listings.update_one(
                {"_id": ObjectId(listing_id)},
                {"$set": {"status": "rescued", "updated_at": _now()}},
            )
        return True, "Claimed quantity updated."
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


def release_claimed_quantity(
    db: Database, listing_id: str, amount: float
) -> tuple[bool, str]:
    """
    Release quantity back to available when a claim is cancelled.
    Resets status to 'available' if no quantity remains claimed.
    """
    try:
        doc = db.food_listings.find_one_and_update(
            {"_id": ObjectId(listing_id)},
            {
                "$inc": {"claimed_quantity": -amount},
                "$set": {"updated_at": _now()},
            },
            return_document=True,
        )
        if doc is None:
            return False, "Listing not found."

        new_claimed = max(0.0, doc["claimed_quantity"] - amount)
        if new_claimed <= 0 and doc["status"] in ("reserved",):
            db.food_listings.update_one(
                {"_id": ObjectId(listing_id)},
                {"$set": {"status": "available", "claimed_quantity": 0.0, "updated_at": _now()}},
            )
        return True, "Quantity released."
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
#  Delete / Archive
# ─────────────────────────────────────────────────────────────────────────────

def delete_listing(db: Database, listing_id: str, donor_id: str) -> tuple[bool, str]:
    """
    Delete a listing only if it belongs to the given donor and has no
    active (pending/confirmed) claims.  Completed/cancelled claims are fine.
    """
    try:
        listing = db.food_listings.find_one({"_id": ObjectId(listing_id)})
        if not listing:
            return False, "Listing not found."
        if str(listing["donor_id"]) != donor_id:
            return False, "You can only delete your own listings."
        if listing["status"] in ("reserved", "rescued"):
            return False, "Cannot delete a listing that has active or completed claims."

        db.food_listings.delete_one({"_id": ObjectId(listing_id)})
        return True, "Listing deleted."
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


def expire_overdue_listings(db: Database) -> int:
    """
    Mark all 'available' or 'reserved' listings whose deadline has passed
    as 'expired'.  Returns the number of listings updated.
    Called at app startup and periodically via the UI.
    """
    try:
        result = db.food_listings.update_many(
            {
                "status": {"$in": ["available", "reserved"]},
                "pickup_deadline": {"$lte": _now()},
            },
            {"$set": {"status": "expired", "updated_at": _now()}},
        )
        return result.modified_count
    except PyMongoError:
        return 0
