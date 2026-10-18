"""
repositories/claim_repo.py
--------------------------
All direct MongoDB operations for the `claims` collection.

Document structure:
  _id              : ObjectId  – primary key
  listing_id       : ObjectId  – references food_listings._id
  claimant_id      : ObjectId  – references users._id (recipient or volunteer)
  claimed_quantity : float     – how much this claimant claimed
  status           : str       – pending | confirmed | completed | cancelled
  created_at       : datetime
  updated_at       : datetime | None
  notes            : str | None

Design note:
  Claims are separate documents (not embedded in listings) because:
  - A single listing can have multiple claims from different recipients.
  - Claims go through a lifecycle (pending → confirmed → completed/cancelled).
  - We need to query claims by claimant independently of listings.
  - Embedding an array of claims in the listing would create unbounded
    document growth and make atomic updates on individual claims harder.
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

def create_claim(db: Database, data: dict) -> tuple[bool, str]:
    """Insert a new claim document. Status starts as 'pending'."""
    doc = {
        "listing_id":       ObjectId(str(data["listing_id"])),
        "claimant_id":      ObjectId(str(data["claimant_id"])),
        "claimed_quantity": float(data["claimed_quantity"]),
        "status":           "pending",
        "created_at":       _now(),
        "updated_at":       None,
        "notes":            data.get("notes", "").strip() or None,
    }
    try:
        result = db.claims.insert_one(doc)
        return True, str(result.inserted_id)
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
#  Read
# ─────────────────────────────────────────────────────────────────────────────

def get_claim_by_id(db: Database, claim_id: str) -> Optional[dict]:
    try:
        return db.claims.find_one({"_id": ObjectId(claim_id)})
    except Exception:
        return None


def get_claims_for_listing(db: Database, listing_id: str) -> list[dict]:
    """All claims for a given listing, newest first."""
    return list(
        db.claims.find({"listing_id": ObjectId(listing_id)}).sort("created_at", -1)
    )


def get_claims_for_user(db: Database, user_id: str, status: Optional[str] = None) -> list[dict]:
    """All claims made by a user, optionally filtered by status."""
    query: dict = {"claimant_id": ObjectId(user_id)}
    if status:
        query["status"] = status
    return list(db.claims.find(query).sort("created_at", -1))


def get_claims_with_details(db: Database, claimant_id: Optional[str] = None) -> list[dict]:
    """
    Return claims joined with listing and claimant details via $lookup.
    Used on the claims management page.
    """
    match = {}
    if claimant_id:
        match["claimant_id"] = ObjectId(claimant_id)

    pipeline = [
        {"$match": match},
        {"$sort": {"created_at": -1}},
        {"$limit": 200},
        # Join with food_listings
        {
            "$lookup": {
                "from": "food_listings",
                "localField": "listing_id",
                "foreignField": "_id",
                "as": "listing",
            }
        },
        {"$unwind": {"path": "$listing", "preserveNullAndEmptyArrays": True}},
        # Join with users (claimant)
        {
            "$lookup": {
                "from": "users",
                "localField": "claimant_id",
                "foreignField": "_id",
                "as": "claimant",
            }
        },
        {"$unwind": {"path": "$claimant", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "claimed_quantity": 1,
                "status": 1,
                "created_at": 1,
                "notes": 1,
                "listing_title":    "$listing.title",
                "listing_category": "$listing.category",
                "pickup_location":  "$listing.pickup_location",
                "pickup_deadline":  "$listing.pickup_deadline",
                "unit":             "$listing.unit",
                "claimant_name":    "$claimant.name",
                "claimant_role":    "$claimant.role",
            }
        },
    ]
    return list(db.claims.aggregate(pipeline))


def count_active_claims_for_listing(db: Database, listing_id: str) -> int:
    """Count pending + confirmed claims for a listing (to prevent over-claiming)."""
    return db.claims.count_documents({
        "listing_id": ObjectId(listing_id),
        "status": {"$in": ["pending", "confirmed"]},
    })


# ─────────────────────────────────────────────────────────────────────────────
#  Update
# ─────────────────────────────────────────────────────────────────────────────

def update_claim_status(
    db: Database, claim_id: str, new_status: str
) -> tuple[bool, str]:
    """Update the status of a claim. Use validate_claim_transition first."""
    try:
        result = db.claims.update_one(
            {"_id": ObjectId(claim_id)},
            {"$set": {"status": new_status, "updated_at": _now()}},
        )
        if result.matched_count == 0:
            return False, "Claim not found."
        return True, f"Claim status updated to '{new_status}'."
    except PyMongoError as exc:
        return False, f"Database error: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
#  Summary queries
# ─────────────────────────────────────────────────────────────────────────────

def get_claim_counts_by_status(db: Database) -> dict:
    """Return {status: count} for all claims."""
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    return {doc["_id"]: doc["count"] for doc in db.claims.aggregate(pipeline)}
