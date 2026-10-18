"""
analytics/pipelines.py
-----------------------
All six required MongoDB aggregation pipelines.

Each pipeline is:
  1. Defined as a plain Python list (the MongoDB aggregation pipeline).
  2. Wrapped in a function that executes it via PyMongo and returns results.
  3. Documented with: purpose, stage-by-stage explanation, example I/O.

Pipeline index
──────────────
  1. total_food_rescued          – Total successfully rescued qty (kg / servings / …)
  2. category_analysis           – Listings and quantities grouped by food category
  3. rescue_success_rate         – Completed vs cancelled vs pending counts + %
  4. location_analysis           – Surplus and rescue counts by pickup location
  5. donor_performance           – Rank donors by rescued qty and successful donations
  6. rescue_trends               – Rescue activity grouped by day/month over time
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pymongo.database import Database


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 1 – Total Food Rescued
# ═════════════════════════════════════════════════════════════════════════════

def pipeline_total_food_rescued(db: Database) -> list[dict]:
    """
    PURPOSE
    ───────
    Calculate the total quantity of food successfully rescued, broken down
    by unit.  Uses rescue_records (immutable audit trail) rather than
    claims or listings, so only food that was actually collected is counted.

    STAGES
    ──────
    $group  – Groups all rescue records by unit of measurement.
              $sum accumulates rescued_quantity; $sum: 1 counts records.

    $sort   – Sorts by total_rescued descending (highest impact first).

    $project – Renames _id → unit, adds a human-readable label.

    EXAMPLE INPUT (rescue_records)
    ─────────────────────────────
    { rescued_quantity: 5.0, unit: "kg" }
    { rescued_quantity: 3.5, unit: "kg" }
    { rescued_quantity: 20,  unit: "servings" }

    EXAMPLE OUTPUT
    ──────────────
    [
      { unit: "kg",       total_rescued: 8.5,  rescue_count: 2 },
      { unit: "servings", total_rescued: 20.0, rescue_count: 1 }
    ]
    """
    pipeline = [
        # Stage 1: Group all records by unit, sum quantity, count records
        {
            "$group": {
                "_id":           "$unit",
                "total_rescued": {"$sum": "$rescued_quantity"},
                "rescue_count":  {"$sum": 1},
            }
        },
        # Stage 2: Sort by total rescued quantity, largest first
        {"$sort": {"total_rescued": -1}},
        # Stage 3: Rename _id to unit for readability
        {
            "$project": {
                "_id":           0,
                "unit":          "$_id",
                "total_rescued": {"$round": ["$total_rescued", 2]},
                "rescue_count":  1,
            }
        },
    ]
    return list(db.rescue_records.aggregate(pipeline))


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 2 – Category Analysis
# ═════════════════════════════════════════════════════════════════════════════

def pipeline_category_analysis(db: Database) -> list[dict]:
    """
    PURPOSE
    ───────
    Group food listings by category to identify which categories have the
    most surplus.  Helps donors and coordinators see where food waste is
    concentrated.

    STAGES
    ──────
    $group   – Groups by category.
               Counts listings; sums total_quantity and claimed_quantity.
               $avg calculates the average available quantity per listing.

    $addFields – Computes remaining (unclaimed) quantity.

    $sort    – Sorts by total_quantity descending.

    $project – Clean output shape.

    EXAMPLE OUTPUT
    ──────────────
    [
      { category: "Cooked Meal", listing_count: 8, total_quantity: 120,
        total_claimed: 45, remaining_quantity: 75, avg_quantity: 15 },
      { category: "Bakery & Bread", listing_count: 4, … }
    ]
    """
    pipeline = [
        # Stage 1: Group by category
        {
            "$group": {
                "_id":             "$category",
                "listing_count":   {"$sum": 1},
                "total_quantity":  {"$sum": "$quantity"},
                "total_claimed":   {"$sum": "$claimed_quantity"},
                "avg_quantity":    {"$avg": "$quantity"},
            }
        },
        # Stage 2: Add computed remaining field
        {
            "$addFields": {
                "remaining_quantity": {
                    "$subtract": ["$total_quantity", "$total_claimed"]
                }
            }
        },
        # Stage 3: Sort by total quantity
        {"$sort": {"total_quantity": -1}},
        # Stage 4: Clean projection
        {
            "$project": {
                "_id":              0,
                "category":         "$_id",
                "listing_count":    1,
                "total_quantity":   {"$round": ["$total_quantity", 2]},
                "total_claimed":    {"$round": ["$total_claimed", 2]},
                "remaining_quantity": {"$round": ["$remaining_quantity", 2]},
                "avg_quantity":     {"$round": ["$avg_quantity", 2]},
            }
        },
    ]
    return list(db.food_listings.aggregate(pipeline))


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 3 – Rescue Success Rate
# ═════════════════════════════════════════════════════════════════════════════

def pipeline_rescue_success_rate(db: Database) -> dict:
    """
    PURPOSE
    ───────
    Calculate how many claims were completed, cancelled, or still pending.
    The completion percentage shows overall rescue effectiveness.

    STAGES
    ──────
    $group   – Single-group (no _id) to count claims per status using $cond.

    $addFields – Computes completion_pct = completed / (completed+cancelled) * 100.
                 The denominator excludes 'pending' so in-flight claims don't
                 distort the metric.

    $project – Final clean shape.

    EXAMPLE OUTPUT
    ──────────────
    {
      completed: 18, cancelled: 4, pending: 3, confirmed: 2,
      total_claims: 27, completion_pct: 81.8
    }
    """
    pipeline = [
        # Stage 1: Count claims per status in one pass
        {
            "$group": {
                "_id": None,
                "completed":  {"$sum": {"$cond": [{"$eq": ["$status", "completed"]},  1, 0]}},
                "cancelled":  {"$sum": {"$cond": [{"$eq": ["$status", "cancelled"]},  1, 0]}},
                "pending":    {"$sum": {"$cond": [{"$eq": ["$status", "pending"]},    1, 0]}},
                "confirmed":  {"$sum": {"$cond": [{"$eq": ["$status", "confirmed"]},  1, 0]}},
                "total":      {"$sum": 1},
            }
        },
        # Stage 2: Compute completion percentage
        {
            "$addFields": {
                "completion_pct": {
                    "$cond": {
                        "if":   {"$gt": [{"$add": ["$completed", "$cancelled"]}, 0]},
                        "then": {
                            "$round": [
                                {
                                    "$multiply": [
                                        {"$divide": [
                                            "$completed",
                                            {"$add": ["$completed", "$cancelled"]},
                                        ]},
                                        100,
                                    ]
                                },
                                1,
                            ]
                        },
                        "else": 0,
                    }
                }
            }
        },
        # Stage 3: Clean output
        {
            "$project": {
                "_id": 0,
                "completed": 1, "cancelled": 1,
                "pending": 1,   "confirmed": 1,
                "total_claims": "$total",
                "completion_pct": 1,
            }
        },
    ]
    results = list(db.claims.aggregate(pipeline))
    if results:
        return results[0]
    return {
        "completed": 0, "cancelled": 0, "pending": 0,
        "confirmed": 0, "total_claims": 0, "completion_pct": 0,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 4 – Location Analysis
# ═════════════════════════════════════════════════════════════════════════════

def pipeline_location_analysis(db: Database) -> list[dict]:
    """
    PURPOSE
    ───────
    Identify which pickup locations generate the most food surplus and
    how many rescues originated from each location.  Useful for
    identifying geographic hotspots of food waste.

    Uses two sub-pipelines and a $unionWith to combine listing counts
    (from food_listings) with rescue counts (from rescue_records).

    NOTE: $unionWith requires MongoDB 4.4+.  If unavailable, the function
    falls back to two separate queries merged in Python.

    STAGES (listings side)
    ──────────────────────
    $group   – Count listings and sum total_quantity per pickup_location.
    $sort    – Most surplus first.

    STAGES (rescue side via $unionWith)
    ────────────────────────────────────
    $group   – Count successful rescues per location.
    $unionWith merges the two result sets.
    A second $group re-aggregates to combine the two streams.

    EXAMPLE OUTPUT
    ──────────────
    [
      { location: "LPU Hostel Block A", listing_count: 6,
        total_quantity: 80, rescue_count: 5 },
      ...
    ]
    """
    # Approach: run two separate aggregations and merge in Python
    # (avoids $unionWith version dependency for broader compatibility).

    # Sub-pipeline A: listings per location
    listings_pipeline = [
        {
            "$group": {
                "_id":            "$pickup_location",
                "listing_count":  {"$sum": 1},
                "total_quantity": {"$sum": "$quantity"},
            }
        },
        {"$sort": {"listing_count": -1}},
        {"$limit": 20},
    ]
    listings_by_loc = {
        doc["_id"]: doc
        for doc in db.food_listings.aggregate(listings_pipeline)
    }

    # Sub-pipeline B: rescues per location
    rescues_pipeline = [
        {
            "$group": {
                "_id":           "$pickup_location",
                "rescue_count":  {"$sum": 1},
                "rescued_total": {"$sum": "$rescued_quantity"},
            }
        },
    ]
    rescues_by_loc = {
        doc["_id"]: doc
        for doc in db.rescue_records.aggregate(rescues_pipeline)
    }

    # Merge
    all_locs = set(listings_by_loc) | set(rescues_by_loc)
    merged = []
    for loc in all_locs:
        l = listings_by_loc.get(loc, {})
        r = rescues_by_loc.get(loc, {})
        merged.append({
            "location":      loc or "Unknown",
            "listing_count": l.get("listing_count", 0),
            "total_quantity": round(l.get("total_quantity", 0), 2),
            "rescue_count":  r.get("rescue_count", 0),
            "rescued_total": round(r.get("rescued_total", 0), 2),
        })

    merged.sort(key=lambda x: x["listing_count"], reverse=True)
    return merged[:15]


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 5 – Donor Performance
# ═════════════════════════════════════════════════════════════════════════════

def pipeline_donor_performance(db: Database) -> list[dict]:
    """
    PURPOSE
    ───────
    Rank donors by their real-world impact: how much food they listed,
    how many listings led to successful rescues, and what percentage of
    their listed food was rescued.

    STAGES
    ──────
    $group   – On rescue_records, group by donor_id. Sum rescued_quantity,
               count successful rescues (each rescue_record = 1 completed
               rescue event), collect distinct food categories donated.

    $lookup  – Join with the `users` collection to get the donor's name
               and location.

    $unwind  – Flatten the donor array from $lookup.

    $sort    – By total_rescued_kg descending (top performers first).

    $project – Final shape with donor details and metrics.

    EXAMPLE OUTPUT
    ──────────────
    [
      { donor_name: "Sunrise Café", total_rescued: 45.5,
        rescue_events: 8, categories: ["Cooked Meal", "Bakery & Bread"] },
      ...
    ]
    """
    pipeline = [
        # Stage 1: Group rescue records by donor
        {
            "$group": {
                "_id":            "$donor_id",
                "total_rescued":  {"$sum": "$rescued_quantity"},
                "rescue_events":  {"$sum": 1},
                "categories":     {"$addToSet": "$category"},
                "locations":      {"$addToSet": "$pickup_location"},
            }
        },
        # Stage 2: Sort by impact
        {"$sort": {"total_rescued": -1}},
        # Stage 3: Join with users to get donor name
        {
            "$lookup": {
                "from":         "users",
                "localField":   "_id",
                "foreignField": "_id",
                "as":           "donor",
            }
        },
        # Stage 4: Flatten donor array
        {"$unwind": {"path": "$donor", "preserveNullAndEmptyArrays": True}},
        # Stage 5: Project final shape
        {
            "$project": {
                "_id":          0,
                "donor_id":     {"$toString": "$_id"},
                "donor_name":   {"$ifNull": ["$donor.name", "Unknown Donor"]},
                "donor_location": {"$ifNull": ["$donor.location", "Unknown"]},
                "total_rescued": {"$round": ["$total_rescued", 2]},
                "rescue_events": 1,
                "categories":   1,
            }
        },
    ]
    return list(db.rescue_records.aggregate(pipeline))


# ═════════════════════════════════════════════════════════════════════════════
#  Pipeline 6 – Rescue Trends
# ═════════════════════════════════════════════════════════════════════════════

def pipeline_rescue_trends(
    db: Database,
    group_by: Literal["day", "month"] = "day",
) -> list[dict]:
    """
    PURPOSE
    ───────
    Show how rescue activity changes over time so coordinators can
    identify growth trends, seasonal patterns, or sudden drops.

    STAGES
    ──────
    $group   – Groups rescue_records by day or month using $dateToString
               to format rescued_at as a string key (e.g. "2026-10-18"
               or "2026-10").  Sums rescued_quantity and counts events.

    $sort    – Chronological order (oldest first for trend charts).

    $project – Human-readable date label and rounded metrics.

    EXAMPLE OUTPUT (group_by="month")
    ──────────────────────────────────
    [
      { period: "2026-09", rescue_count: 12, total_rescued: 68.5 },
      { period: "2026-10", rescue_count: 18, total_rescued: 104.0 },
    ]
    """
    date_format = "%Y-%m-%d" if group_by == "day" else "%Y-%m"

    pipeline = [
        # Stage 1: Group by formatted date string
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": date_format,
                        "date":   "$rescued_at",
                    }
                },
                "rescue_count":  {"$sum": 1},
                "total_rescued": {"$sum": "$rescued_quantity"},
            }
        },
        # Stage 2: Sort chronologically
        {"$sort": {"_id": 1}},
        # Stage 3: Rename for clarity
        {
            "$project": {
                "_id":          0,
                "period":       "$_id",
                "rescue_count": 1,
                "total_rescued": {"$round": ["$total_rescued", 2]},
            }
        },
    ]
    return list(db.rescue_records.aggregate(pipeline))


# ═════════════════════════════════════════════════════════════════════════════
#  Dashboard summary (calls multiple pipelines for the home page)
# ═════════════════════════════════════════════════════════════════════════════

def get_dashboard_summary(db: Database) -> dict:
    """
    Aggregates key metrics for the home dashboard.
    Each value is sourced from a real MongoDB query – nothing is hardcoded.

    Returns a flat dict of metric_name → value.
    """
    from config import KG_TO_MEALS_ESTIMATE

    # Active listings
    active_listings = db.food_listings.count_documents(
        {"status": "available", "pickup_deadline": {"$gt": datetime.now(timezone.utc)}}
    )

    # Expired listings
    expired_listings = db.food_listings.count_documents({"status": "expired"})

    # Total rescued (kg equivalent – only kg records for meal estimate)
    rescued_totals = pipeline_total_food_rescued(db)
    total_rescued_kg = next(
        (r["total_rescued"] for r in rescued_totals if r["unit"] == "kg"), 0.0
    )
    # Meals estimate (clearly labelled as an estimate)
    estimated_meals = round(total_rescued_kg * KG_TO_MEALS_ESTIMATE)

    # Claim counts
    claim_stats = pipeline_rescue_success_rate(db)

    # Total listings ever
    total_listings = db.food_listings.count_documents({})

    # Total registered users
    total_users = db.users.count_documents({})

    return {
        "active_listings":   active_listings,
        "expired_listings":  expired_listings,
        "total_listings":    total_listings,
        "total_rescued_kg":  round(total_rescued_kg, 2),
        "estimated_meals":   estimated_meals,   # ← labelled as estimate in UI
        "completed_rescues": claim_stats["completed"],
        "pending_claims":    claim_stats["pending"],
        "cancelled_claims":  claim_stats["cancelled"],
        "completion_pct":    claim_stats["completion_pct"],
        "total_users":       total_users,
        "rescued_totals":    rescued_totals,    # per-unit breakdown
    }
