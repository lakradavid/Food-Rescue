"""
ui_pages/query_explorer.py
--------------------------
Query Explorer – Live MongoDB Query Demonstration Page

Designed for viva / faculty demo.  Organised into three sections:

  Section A – CRUD Queries
    A1. Find all available listings           (find + filter)
    A2. Find listing by ID                    (find_one)
    A3. Find listings by category + location  (multi-field filter)
    A4. Find listings expiring soon           (range query on date)
    A5. Count documents by status             (count_documents)
    A6. Insert a test listing                 (insert_one)
    A7. Update listing status                 (update_one + $set)
    A8. Delete a listing                      (delete_one – test doc only)

  Section B – Aggregation Pipelines
    B1. Total food rescued by unit            (Pipeline 1)
    B2. Category analysis                     (Pipeline 2)
    B3. Rescue success rate                   (Pipeline 3)
    B4. Location analysis                     (Pipeline 4)
    B5. Donor performance ranking             (Pipeline 5)
    B6. Rescue trends over time               (Pipeline 6)

  Section C – Advanced / Compound Queries
    C1. $lookup – listings with donor names
    C2. $unwind + $group – claims per listing
    C3. $match + $project – active listings, selected fields only
    C4. $sort + $limit  – top 5 most generous donors
    C5. Text search simulation with $regex
    C6. Compound index query – status + deadline together

Every query shows:
  • The MongoDB query / pipeline in a code block (copy-paste ready)
  • A "Run" button that executes it live against the database
  • The result in a formatted table or JSON viewer
  • A plain-English explanation of every operator used
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

import streamlit as st
import pandas as pd
from bson import ObjectId
from bson.json_util import dumps as bson_dumps

from database import get_db
from config import FOOD_CATEGORIES, QUANTITY_UNITS


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(docs: list[dict]) -> pd.DataFrame:
    """Convert a list of Mongo docs to a display-friendly DataFrame."""
    if not docs:
        return pd.DataFrame()
    rows = []
    for d in docs:
        row = {}
        for k, v in d.items():
            if isinstance(v, ObjectId):
                row[k] = str(v)
            elif isinstance(v, datetime):
                row[k] = v.strftime("%d %b %Y %H:%M")
            elif isinstance(v, list):
                row[k] = ", ".join(str(i) for i in v) if v else "—"
            else:
                row[k] = v if v is not None else "—"
        rows.append(row)
    return pd.DataFrame(rows)


def _show_result(docs: list[dict] | dict | int | float, label: str = "Result") -> None:
    """Render query result as a table (list) or JSON (dict/scalar)."""
    if isinstance(docs, list):
        if not docs:
            st.info("Query returned 0 documents.")
            return
        st.success(f"✅ {label}: **{len(docs)}** document(s) returned")
        st.dataframe(_fmt(docs), hide_index=True, use_container_width=True)
    elif isinstance(docs, dict):
        st.success(f"✅ {label}")
        st.json(json.loads(bson_dumps(docs)))
    else:
        st.success(f"✅ {label}: **{docs}**")


def _code(snippet: str) -> None:
    """Render a MongoDB query snippet in a code block."""
    st.code(snippet, language="python")


def _explain(text: str) -> None:
    st.info(f"💡 **Explanation:** {text}")


# ─────────────────────────────────────────────────────────────────────────────
#  Main render
# ─────────────────────────────────────────────────────────────────────────────

def render() -> None:
    st.title("🔬 Query Explorer")
    st.caption(
        "Live MongoDB query demonstration. Every query runs against the real "
        "database and shows actual results.  Use this page during your viva to "
        "walk through CRUD operations and aggregation pipelines."
    )

    db = get_db()

    sec_a, sec_b, sec_c = st.tabs([
        "📄 A — CRUD Queries",
        "📊 B — Aggregation Pipelines",
        "🔗 C — Advanced Queries",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION A – CRUD Queries
    # ══════════════════════════════════════════════════════════════════════════
    with sec_a:
        st.header("CRUD Query Demonstrations")
        st.caption("All queries run live against the `foodrescue` database.")

        # ── A1. Find all available listings ───────────────────────────────────
        with st.expander("A1 — Find all AVAILABLE listings (find + filter)", expanded=True):
            _code("""\
# MongoDB Query
db.food_listings.find(
    { "status": "available" },
    { "title": 1, "category": 1, "quantity": 1,
      "unit": 1, "pickup_location": 1, "pickup_deadline": 1 }
).sort("pickup_deadline", 1)
""")
            _explain(
                "`find()` scans the `food_listings` collection with a filter document "
                "`{ status: 'available' }`. The second argument is a **projection** — "
                "`1` means include the field, `0` means exclude. "
                "`.sort('pickup_deadline', 1)` orders results ascending (earliest deadline first). "
                "This uses the `listings_status` index defined in `database.py`."
            )
            if st.button("▶ Run A1", key="a1"):
                docs = list(
                    db.food_listings.find(
                        {"status": "available"},
                        {"title": 1, "category": 1, "quantity": 1,
                         "unit": 1, "pickup_location": 1, "pickup_deadline": 1},
                    ).sort("pickup_deadline", 1)
                )
                _show_result(docs, "Available listings")

        # ── A2. Find listing by ID ─────────────────────────────────────────────
        with st.expander("A2 — Find a single listing by ObjectId (find_one)"):
            st.caption("Pick any listing from the dropdown to look it up by its _id.")
            all_listings = list(db.food_listings.find({}, {"title": 1}))
            if all_listings:
                id_map = {f"{l['title']} — {str(l['_id'])[:10]}…": str(l["_id"]) for l in all_listings}
                chosen_label = st.selectbox("Select listing:", list(id_map.keys()), key="a2_sel")
                chosen_id = id_map[chosen_label]
                _code(f"""\
# MongoDB Query
db.food_listings.find_one(
    {{ "_id": ObjectId("{chosen_id}") }}
)
""")
                _explain(
                    "`find_one()` returns the first matching document or `None`. "
                    "`ObjectId()` converts the 24-character hex string into a BSON ObjectId "
                    "for comparison — MongoDB stores `_id` as ObjectId, not as a plain string. "
                    "This hits the default `_id` index, making the lookup O(log n)."
                )
                if st.button("▶ Run A2", key="a2"):
                    doc = db.food_listings.find_one({"_id": ObjectId(chosen_id)})
                    _show_result(doc, "Listing document")
            else:
                st.info("No listings in the database yet.")

        # ── A3. Multi-field filter ─────────────────────────────────────────────
        with st.expander("A3 — Filter by category AND location (multi-field query)"):
            col1, col2 = st.columns(2)
            with col1:
                sel_cat = st.selectbox("Category:", FOOD_CATEGORIES, key="a3_cat")
            with col2:
                loc_kw = st.text_input("Location keyword:", value="LPU", key="a3_loc")

            _code(f"""\
# MongoDB Query – AND of two conditions
db.food_listings.find({{
    "category":        "{sel_cat}",
    "pickup_location": {{ "$regex": "{loc_kw}", "$options": "i" }},
    "status":          "available"
}})
""")
            _explain(
                "Multiple keys in the filter document are implicitly **AND**ed together. "
                "`$regex` performs a regular-expression search on the string field — "
                "`$options: 'i'` makes it case-insensitive. "
                "This is a partial-match search, equivalent to SQL `LIKE '%LPU%'`. "
                "For exact equality on `category` and `status`, we use plain string values. "
                "MongoDB checks the `listings_status_deadline` compound index first."
            )
            if st.button("▶ Run A3", key="a3"):
                docs = list(db.food_listings.find({
                    "category":        sel_cat,
                    "pickup_location": {"$regex": loc_kw, "$options": "i"},
                    "status":          "available",
                }))
                _show_result(docs, f"Listings — {sel_cat} near '{loc_kw}'")

        # ── A4. Range query on date ────────────────────────────────────────────
        with st.expander("A4 — Listings expiring within next N hours (date range query)"):
            hours = st.slider("Within next … hours:", 1, 48, 6, key="a4_hours")
            cutoff = _now() + timedelta(hours=hours)

            _code(f"""\
# MongoDB Query – date range with $gt and $lte
from datetime import datetime, timezone, timedelta

now    = datetime.now(timezone.utc)
cutoff = now + timedelta(hours={hours})

db.food_listings.find({{
    "status":          "available",
    "pickup_deadline": {{
        "$gt":  now,      # deadline is still in the future
        "$lte": cutoff    # but within the next {hours} hours
    }}
}}).sort("pickup_deadline", 1)
""")
            _explain(
                "`$gt` (greater than) and `$lte` (less than or equal) are **comparison operators**. "
                "MongoDB stores timestamps as BSON Date objects, so Python `datetime` values "
                "are directly comparable. Together `$gt now` and `$lte cutoff` form a half-open "
                f"time window: now < deadline ≤ now+{hours}h. "
                "This is used by the urgency alert system on the home dashboard."
            )
            if st.button("▶ Run A4", key="a4"):
                docs = list(
                    db.food_listings.find({
                        "status": "available",
                        "pickup_deadline": {"$gt": _now(), "$lte": cutoff},
                    }).sort("pickup_deadline", 1)
                )
                _show_result(docs, f"Listings expiring within {hours} hours")

        # ── A5. Count by status ────────────────────────────────────────────────
        with st.expander("A5 — Count documents by status (count_documents)"):
            _code("""\
# Count separately for each status value
statuses = ["available", "reserved", "rescued", "expired"]
counts   = {}
for s in statuses:
    counts[s] = db.food_listings.count_documents({ "status": s })

# Also count ALL listings
counts["total"] = db.food_listings.count_documents({})
""")
            _explain(
                "`count_documents(filter)` returns the number of documents matching the filter. "
                "Passing `{}` (empty filter) counts everything. "
                "It uses collection metadata and indexes efficiently — "
                "much faster than fetching all documents and using Python `len()`. "
                "Equivalent to SQL `SELECT COUNT(*) WHERE status = 'available'`."
            )
            if st.button("▶ Run A5", key="a5"):
                counts = {s: db.food_listings.count_documents({"status": s})
                          for s in ["available", "reserved", "rescued", "expired"]}
                counts["TOTAL"] = db.food_listings.count_documents({})
                df = pd.DataFrame(
                    [{"Status": k, "Count": v} for k, v in counts.items()]
                )
                st.success("✅ Listing counts by status")
                st.dataframe(df, hide_index=True, use_container_width=True)

        # ── A6. Insert ────────────────────────────────────────────────────────
        with st.expander("A6 — Insert a test document (insert_one)"):
            _code("""\
# MongoDB Insert
test_doc = {
    "title":            "Demo Food Item (Query Explorer)",
    "category":         "Packaged Food",
    "description":      "Inserted via Query Explorer for demo purposes.",
    "quantity":         5.0,
    "claimed_quantity": 0.0,
    "unit":             "kg",
    "donor_id":         <first_donor_ObjectId>,
    "pickup_location":  "Query Explorer Demo Location",
    "status":           "available",
    "prepared_at":      datetime.now(timezone.utc),
    "pickup_deadline":  datetime.now(timezone.utc) + timedelta(hours=6),
    "allergens":        [],
    "created_at":       datetime.now(timezone.utc),
    "updated_at":       None,
}
result = db.food_listings.insert_one(test_doc)
print(result.inserted_id)   # the new ObjectId
""")
            _explain(
                "`insert_one()` inserts a single document and returns an `InsertOneResult` object. "
                "`result.inserted_id` gives the auto-generated `_id` (BSON ObjectId). "
                "MongoDB generates the `_id` if you don't provide one. "
                "The document must pass the collection's **JSON Schema validator** we defined in "
                "`database.py` — required fields, enum values, and numeric ranges are all enforced "
                "at the database level before the write is accepted."
            )
            if st.button("▶ Run A6 — Insert test doc", key="a6"):
                donor = db.users.find_one({"role": "donor"})
                if not donor:
                    st.error("No donor found. Run the seed script first.")
                else:
                    # Only insert if not already there (idempotent demo)
                    existing = db.food_listings.find_one({"title": "Demo Food Item (Query Explorer)"})
                    if existing:
                        st.warning(f"Test document already exists — ID: `{existing['_id']}`")
                    else:
                        res = db.food_listings.insert_one({
                            "title":            "Demo Food Item (Query Explorer)",
                            "category":         "Packaged Food",
                            "description":      "Inserted via Query Explorer for demo.",
                            "quantity":         5.0,
                            "claimed_quantity": 0.0,
                            "unit":             "kg",
                            "donor_id":         donor["_id"],
                            "pickup_location":  "Query Explorer Demo Location",
                            "status":           "available",
                            "prepared_at":      _now(),
                            "pickup_deadline":  _now() + timedelta(hours=6),
                            "allergens":        [],
                            "created_at":       _now(),
                            "updated_at":       None,
                        })
                        st.success(f"✅ Inserted! New `_id`: `{res.inserted_id}`")

        # ── A7. Update ────────────────────────────────────────────────────────
        with st.expander("A7 — Update a field with $set (update_one)"):
            _code("""\
# MongoDB Update – $set modifies only specified fields
result = db.food_listings.update_one(
    { "title": "Demo Food Item (Query Explorer)" },   # filter
    { "$set": {
        "description": "Updated description — demonstrating $set operator",
        "updated_at":  datetime.now(timezone.utc)
    }}
)
print(result.matched_count)   # how many docs matched the filter
print(result.modified_count)  # how many were actually changed
""")
            _explain(
                "`update_one()` modifies the **first** document matching the filter. "
                "`$set` replaces only the named fields — all other fields remain untouched. "
                "This is the safe way to do partial updates. "
                "Without `$set` you would accidentally replace the entire document. "
                "`matched_count` vs `modified_count` lets you detect if the document "
                "existed but already had the same value (matched=1, modified=0)."
            )
            if st.button("▶ Run A7 — Update test doc", key="a7"):
                res = db.food_listings.update_one(
                    {"title": "Demo Food Item (Query Explorer)"},
                    {"$set": {
                        "description": "Updated description — demonstrating $set operator",
                        "updated_at":  _now(),
                    }},
                )
                if res.matched_count == 0:
                    st.warning("Test document not found. Run A6 first to insert it.")
                else:
                    st.success(
                        f"✅ Matched: **{res.matched_count}** · "
                        f"Modified: **{res.modified_count}**"
                    )
                    doc = db.food_listings.find_one({"title": "Demo Food Item (Query Explorer)"})
                    _show_result(doc, "Updated document")

        # ── A8. Delete ────────────────────────────────────────────────────────
        with st.expander("A8 — Delete the test document (delete_one)"):
            _code("""\
# MongoDB Delete – removes the first matching document
result = db.food_listings.delete_one(
    { "title": "Demo Food Item (Query Explorer)" }
)
print(result.deleted_count)   # 1 if found and deleted, 0 if not found
""")
            _explain(
                "`delete_one()` removes the first document matching the filter. "
                "`result.deleted_count` tells you whether a document was actually found. "
                "In production code we always check this instead of assuming the delete worked. "
                "For bulk deletes across many documents, use `delete_many()` with a broad filter — "
                "but be careful, it has no undo in MongoDB without a backup."
            )
            if st.button("▶ Run A8 — Delete test doc", key="a8"):
                res = db.food_listings.delete_one({"title": "Demo Food Item (Query Explorer)"})
                if res.deleted_count == 0:
                    st.warning("Test document not found. Insert it first with A6.")
                else:
                    st.success(f"✅ Deleted {res.deleted_count} document.")

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION B – Aggregation Pipelines
    # ══════════════════════════════════════════════════════════════════════════
    with sec_b:
        st.header("Aggregation Pipeline Demonstrations")
        st.caption(
            "Aggregation pipelines process documents through a sequence of **stages**. "
            "Each stage transforms the document stream and passes it to the next stage. "
            "This is MongoDB's equivalent of SQL GROUP BY, JOIN, and window functions combined."
        )

        # ── B1. Total food rescued ────────────────────────────────────────────
        with st.expander("B1 — Total food rescued by unit  ($group · $sort · $project)", expanded=True):
            _code("""\
# Pipeline 1 — runs on: rescue_records collection
pipeline = [
    # Stage 1: Group ALL documents by unit, sum quantities, count rescues
    { "$group": {
        "_id":           "$unit",          # group key
        "total_rescued": { "$sum": "$rescued_quantity" },
        "rescue_count":  { "$sum": 1 }     # count each doc as 1
    }},

    # Stage 2: Sort by total rescued (largest first)
    { "$sort": { "total_rescued": -1 } },

    # Stage 3: Rename _id → unit for readable output; round to 2 dp
    { "$project": {
        "_id":           0,                # exclude the _id field
        "unit":          "$_id",
        "total_rescued": { "$round": ["$total_rescued", 2] },
        "rescue_count":  1
    }}
]
results = list(db.rescue_records.aggregate(pipeline))
""")
            _explain(
                "**$group** is the core aggregation operator. `_id` sets the grouping key — "
                "here `'$unit'` means group by the value of the `unit` field. "
                "**$sum** accumulates values: `'$rescued_quantity'` sums the field across all docs "
                "in the group; `1` counts documents. "
                "**$sort** with `-1` means descending. "
                "**$project** reshapes output: `0` hides a field, `1` includes it, "
                "and expressions like `'$_id'` rename fields. "
                "**$round** rounds to 2 decimal places. "
                "Only `rescue_records` are used — cancelled claims never generate a rescue record, "
                "so this count is accurate."
            )
            if st.button("▶ Run B1", key="b1"):
                from analytics.pipelines import pipeline_total_food_rescued
                data = pipeline_total_food_rescued(db)
                _show_result(data, "Total food rescued by unit")

        # ── B2. Category analysis ─────────────────────────────────────────────
        with st.expander("B2 — Category analysis  ($group · $addFields · $sort · $project)"):
            _code("""\
# Pipeline 2 — runs on: food_listings collection
pipeline = [
    # Stage 1: Group by category, aggregate metrics
    { "$group": {
        "_id":            "$category",
        "listing_count":  { "$sum": 1 },
        "total_quantity": { "$sum": "$quantity" },
        "total_claimed":  { "$sum": "$claimed_quantity" },
        "avg_quantity":   { "$avg": "$quantity" }
    }},

    # Stage 2: Add a computed field (not possible inside $group itself)
    { "$addFields": {
        "remaining_quantity": {
            "$subtract": ["$total_quantity", "$total_claimed"]
        }
    }},

    # Stage 3: Sort by total listed quantity
    { "$sort": { "total_quantity": -1 } },

    # Stage 4: Clean final output
    { "$project": {
        "_id": 0, "category": "$_id",
        "listing_count": 1, "total_quantity": 1,
        "total_claimed": 1, "remaining_quantity": 1,
        "avg_quantity": { "$round": ["$avg_quantity", 2] }
    }}
]
results = list(db.food_listings.aggregate(pipeline))
""")
            _explain(
                "**$avg** calculates the mean of `quantity` within each category group. "
                "**$addFields** adds new fields to documents without removing existing ones — "
                "it is the right place for computed fields that depend on values from `$group`. "
                "**$subtract** is an arithmetic expression: `[total, claimed]` → `total - claimed`. "
                "The pipeline runs on ALL listings (available + rescued + expired) giving a "
                "full historical picture of what categories generate the most surplus."
            )
            if st.button("▶ Run B2", key="b2"):
                from analytics.pipelines import pipeline_category_analysis
                data = pipeline_category_analysis(db)
                _show_result(data, "Category analysis")

        # ── B3. Rescue success rate ───────────────────────────────────────────
        with st.expander("B3 — Rescue success rate  ($group with $cond · $addFields · $project)"):
            _code("""\
# Pipeline 3 — runs on: claims collection
pipeline = [
    # Stage 1: Single group (no _id) counts claims per status in ONE pass
    { "$group": {
        "_id":       None,       # None = all documents in one group
        "completed": { "$sum": { "$cond": [{ "$eq": ["$status","completed"] }, 1, 0] }},
        "cancelled": { "$sum": { "$cond": [{ "$eq": ["$status","cancelled"] }, 1, 0] }},
        "pending":   { "$sum": { "$cond": [{ "$eq": ["$status","pending"]   }, 1, 0] }},
        "confirmed": { "$sum": { "$cond": [{ "$eq": ["$status","confirmed"] }, 1, 0] }},
        "total":     { "$sum": 1 }
    }},

    # Stage 2: Compute completion % — exclude pending from denominator
    { "$addFields": {
        "completion_pct": {
            "$cond": {
                "if":   { "$gt": [{ "$add": ["$completed","$cancelled"] }, 0] },
                "then": { "$round": [
                    { "$multiply": [
                        { "$divide": ["$completed", { "$add": ["$completed","$cancelled"] }] },
                        100
                    ]}, 1
                ]},
                "else": 0
            }
        }
    }},

    # Stage 3: Final output shape
    { "$project": {
        "_id": 0, "completed": 1, "cancelled": 1,
        "pending": 1, "confirmed": 1,
        "total_claims": "$total", "completion_pct": 1
    }}
]
results = list(db.claims.aggregate(pipeline))
""")
            _explain(
                "Setting `_id: None` in `$group` collapses ALL documents into a single group — "
                "useful for computing global aggregates. "
                "**$cond** is a conditional expression: `[condition, valueIfTrue, valueIfFalse]`. "
                "**$eq** checks equality. Together `$sum + $cond + $eq` count only documents "
                "where status equals a specific value, all in one pass over the collection. "
                "The completion percentage divides completed by (completed + cancelled) — "
                "pending claims are in-flight and excluded so they don't unfairly deflate the rate. "
                "**$divide** and **$multiply** are arithmetic expression operators."
            )
            if st.button("▶ Run B3", key="b3"):
                from analytics.pipelines import pipeline_rescue_success_rate
                data = pipeline_rescue_success_rate(db)
                _show_result(data, "Rescue success rate")

        # ── B4. Location analysis ─────────────────────────────────────────────
        with st.expander("B4 — Location analysis  (two $group pipelines + Python merge)"):
            _code("""\
# Pipeline 4 — combines food_listings + rescue_records
# (Two separate aggregations merged in Python for MongoDB version compatibility)

# Sub-pipeline A: listings per location
pipeline_A = [
    { "$group": {
        "_id":            "$pickup_location",
        "listing_count":  { "$sum": 1 },
        "total_quantity": { "$sum": "$quantity" }
    }},
    { "$sort": { "listing_count": -1 } },
    { "$limit": 20 }
]
listings_by_loc = { doc["_id"]: doc
    for doc in db.food_listings.aggregate(pipeline_A) }

# Sub-pipeline B: rescues per location
pipeline_B = [
    { "$group": {
        "_id":           "$pickup_location",
        "rescue_count":  { "$sum": 1 },
        "rescued_total": { "$sum": "$rescued_quantity" }
    }}
]
rescues_by_loc = { doc["_id"]: doc
    for doc in db.rescue_records.aggregate(pipeline_B) }

# Merge the two result sets in Python
all_locs = set(listings_by_loc) | set(rescues_by_loc)
merged   = [{ "location": loc,
              "listing_count":  listings_by_loc.get(loc, {}).get("listing_count", 0),
              "total_quantity": listings_by_loc.get(loc, {}).get("total_quantity", 0),
              "rescue_count":   rescues_by_loc.get(loc, {}).get("rescue_count", 0),
              "rescued_total":  rescues_by_loc.get(loc, {}).get("rescued_total", 0) }
            for loc in all_locs]
merged.sort(key=lambda x: x["listing_count"], reverse=True)
""")
            _explain(
                "This pipeline queries **two collections** and merges results. "
                "An alternative is MongoDB's `$unionWith` stage (requires v4.4+), but splitting "
                "into two pipelines and merging in Python is compatible with all MongoDB versions. "
                "**$limit** reduces the result set to the top 20 locations before the merge. "
                "The Python `set` union (`|`) collects all unique locations from both sides. "
                "This approach clearly shows that a location can have listings but no rescues "
                "(food was listed but nobody collected it) — an important insight for waste reduction."
            )
            if st.button("▶ Run B4", key="b4"):
                from analytics.pipelines import pipeline_location_analysis
                data = pipeline_location_analysis(db)
                _show_result(data, "Location analysis")

        # ── B5. Donor performance ─────────────────────────────────────────────
        with st.expander("B5 — Donor performance  ($group · $sort · $lookup · $unwind · $project)"):
            _code("""\
# Pipeline 5 — runs on: rescue_records, joins with users
pipeline = [
    # Stage 1: Group rescue records by donor_id
    { "$group": {
        "_id":           "$donor_id",
        "total_rescued": { "$sum": "$rescued_quantity" },
        "rescue_events": { "$sum": 1 },
        "categories":    { "$addToSet": "$category" },   # unique set
    }},

    # Stage 2: Sort by impact — most rescued first
    { "$sort": { "total_rescued": -1 } },

    # Stage 3: JOIN with users collection to get donor name
    { "$lookup": {
        "from":         "users",      # collection to join
        "localField":   "_id",        # field in rescue_records (donor_id)
        "foreignField": "_id",        # field in users (_id)
        "as":           "donor"       # output array name
    }},

    # Stage 4: Flatten the donor array (lookup always returns an array)
    { "$unwind": {
        "path": "$donor",
        "preserveNullAndEmptyArrays": True   # keep docs even if no match
    }},

    # Stage 5: Final output shape
    { "$project": {
        "_id": 0,
        "donor_name":     { "$ifNull": ["$donor.name", "Unknown"] },
        "donor_location": { "$ifNull": ["$donor.location", "—"] },
        "total_rescued":  { "$round": ["$total_rescued", 2] },
        "rescue_events":  1,
        "categories":     1
    }}
]
results = list(db.rescue_records.aggregate(pipeline))
""")
            _explain(
                "**$lookup** is MongoDB's JOIN operator. It looks up documents from a foreign "
                "collection (`users`) where `foreignField` matches `localField`, and appends "
                "the results as an array field (`donor`). "
                "Because a lookup can match multiple documents, it always returns an **array**. "
                "**$unwind** flattens that array — one output document per array element. "
                "`preserveNullAndEmptyArrays: True` ensures donors without a matching user "
                "document still appear (defensive programming). "
                "**$addToSet** builds a set of unique values — useful for collecting all distinct "
                "food categories a donor has contributed. "
                "**$ifNull** returns a fallback value when the field is null or missing."
            )
            if st.button("▶ Run B5", key="b5"):
                from analytics.pipelines import pipeline_donor_performance
                data = pipeline_donor_performance(db)
                _show_result(data, "Donor performance ranking")

        # ── B6. Rescue trends ─────────────────────────────────────────────────
        with st.expander("B6 — Rescue trends over time  ($group + $dateToString · $sort · $project)"):
            granularity = st.radio("Group by:", ["day", "month"], horizontal=True, key="b6_gran")
            date_fmt    = "%Y-%m-%d" if granularity == "day" else "%Y-%m"

            _code(f"""\
# Pipeline 6 — runs on: rescue_records
date_format = "{date_fmt}"   # "%Y-%m-%d" for day, "%Y-%m" for month

pipeline = [
    # Stage 1: Group by formatted date string
    {{ "$group": {{
        "_id": {{
            "$dateToString": {{
                "format": date_format,
                "date":   "$rescued_at"    # BSON Date field
            }}
        }},
        "rescue_count":  {{ "$sum": 1 }},
        "total_rescued": {{ "$sum": "$rescued_quantity" }}
    }}}},

    # Stage 2: Sort chronologically (oldest first — good for trend charts)
    {{ "$sort": {{ "_id": 1 }} }},

    # Stage 3: Rename _id to period
    {{ "$project": {{
        "_id":           0,
        "period":        "$_id",
        "rescue_count":  1,
        "total_rescued": {{ "$round": ["$total_rescued", 2] }}
    }}}}
]
results = list(db.rescue_records.aggregate(pipeline))
""")
            _explain(
                "**$dateToString** converts a BSON Date to a formatted string, acting as the "
                "group key. `'%Y-%m-%d'` gives daily granularity; `'%Y-%m'` gives monthly. "
                "This is how MongoDB handles time-series grouping — there is no native "
                "`GROUP BY DATE_TRUNC` like in SQL, but `$dateToString` achieves the same result. "
                "Sorting by `_id` after grouping sorts chronologically because the formatted "
                "date string `'YYYY-MM-DD'` sorts lexicographically in the correct time order. "
                "The result feeds directly into the trend line chart on the Analytics page."
            )
            if st.button("▶ Run B6", key="b6"):
                from analytics.pipelines import pipeline_rescue_trends
                data = pipeline_rescue_trends(db, group_by=granularity)
                _show_result(data, f"Rescue trends by {granularity}")

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION C – Advanced / Compound Queries
    # ══════════════════════════════════════════════════════════════════════════
    with sec_c:
        st.header("Advanced & Compound Query Demonstrations")

        # ── C1. $lookup join ──────────────────────────────────────────────────
        with st.expander("C1 — $lookup: listings with donor names (JOIN)", expanded=True):
            _code("""\
# Join food_listings with users to show donor names inline
pipeline = [
    { "$match": {
        "status": { "$in": ["available", "reserved"] },
        "pickup_deadline": { "$gt": datetime.now(timezone.utc) }
    }},
    { "$sort":  { "pickup_deadline": 1 } },
    { "$limit": 10 },
    { "$lookup": {
        "from":         "users",
        "localField":   "donor_id",
        "foreignField": "_id",
        "as":           "donor"
    }},
    { "$unwind": { "path": "$donor", "preserveNullAndEmptyArrays": True } },
    { "$project": {
        "title":           1,
        "category":        1,
        "quantity":        1,
        "unit":            1,
        "pickup_location": 1,
        "pickup_deadline": 1,
        "donor_name":      "$donor.name",
        "donor_phone":     "$donor.phone"
    }}
]
""")
            _explain(
                "This is the standard pattern for **denormalising a reference** at read time. "
                "Users are stored separately (normalised design) and joined here with `$lookup`. "
                "`$match` at the top of the pipeline filters early — MongoDB optimises this to "
                "use the `listings_status_deadline` compound index before doing the join. "
                "Filtering before `$lookup` is always more efficient than filtering after."
            )
            if st.button("▶ Run C1", key="c1"):
                pipeline = [
                    {"$match": {"status": {"$in": ["available", "reserved"]},
                                "pickup_deadline": {"$gt": _now()}}},
                    {"$sort":  {"pickup_deadline": 1}},
                    {"$limit": 10},
                    {"$lookup": {"from": "users", "localField": "donor_id",
                                 "foreignField": "_id", "as": "donor"}},
                    {"$unwind": {"path": "$donor", "preserveNullAndEmptyArrays": True}},
                    {"$project": {"title": 1, "category": 1, "quantity": 1, "unit": 1,
                                  "pickup_location": 1, "pickup_deadline": 1,
                                  "donor_name": "$donor.name",
                                  "donor_phone": "$donor.phone"}},
                ]
                _show_result(list(db.food_listings.aggregate(pipeline)),
                             "Listings with donor names")

        # ── C2. $unwind + $group — claims per listing ─────────────────────────
        with st.expander("C2 — Claims count per listing ($group on claims)"):
            _code("""\
# How many claims does each listing have, broken down by status?
pipeline = [
    { "$group": {
        "_id":    "$listing_id",
        "total":  { "$sum": 1 },
        "pending":   { "$sum": { "$cond": [{ "$eq": ["$status","pending"]   },1,0] }},
        "confirmed": { "$sum": { "$cond": [{ "$eq": ["$status","confirmed"] },1,0] }},
        "completed": { "$sum": { "$cond": [{ "$eq": ["$status","completed"] },1,0] }},
        "cancelled": { "$sum": { "$cond": [{ "$eq": ["$status","cancelled"] },1,0] }},
    }},
    { "$sort": { "total": -1 } },
    { "$project": {
        "_id": 0, "listing_id": { "$toString": "$_id" },
        "total": 1, "pending": 1, "confirmed": 1,
        "completed": 1, "cancelled": 1
    }}
]
""")
            _explain(
                "Grouping the `claims` collection by `listing_id` shows how contested each "
                "listing is. Using `$toString` on `_id` converts the ObjectId to a readable string "
                "in the output. This query is useful for identifying popular listings "
                "(many claims) vs ignored ones (zero claims after days of being available)."
            )
            if st.button("▶ Run C2", key="c2"):
                pipeline = [
                    {"$group": {
                        "_id":       "$listing_id",
                        "total":     {"$sum": 1},
                        "pending":   {"$sum": {"$cond": [{"$eq": ["$status","pending"]},   1, 0]}},
                        "confirmed": {"$sum": {"$cond": [{"$eq": ["$status","confirmed"]}, 1, 0]}},
                        "completed": {"$sum": {"$cond": [{"$eq": ["$status","completed"]}, 1, 0]}},
                        "cancelled": {"$sum": {"$cond": [{"$eq": ["$status","cancelled"]}, 1, 0]}},
                    }},
                    {"$sort": {"total": -1}},
                    {"$project": {"_id": 0, "listing_id": {"$toString": "$_id"},
                                  "total": 1, "pending": 1, "confirmed": 1,
                                  "completed": 1, "cancelled": 1}},
                ]
                _show_result(list(db.claims.aggregate(pipeline)), "Claims per listing")

        # ── C3. $match + $project — selected fields ───────────────────────────
        with st.expander("C3 — $match + $project: active listings, selected fields only"):
            _code("""\
# Retrieve only specific fields from active listings (projection)
pipeline = [
    { "$match": {
        "status":          "available",
        "pickup_deadline": { "$gt": datetime.now(timezone.utc) },
        "claimed_quantity": { "$lt": { "$toDouble": "$quantity" } }
        # ↑ listings that still have unclaimed quantity
    }},
    { "$project": {
        "_id":             0,
        "title":           1,
        "category":        1,
        "available":       { "$subtract": ["$quantity", "$claimed_quantity"] },
        "unit":            1,
        "pickup_location": 1,
        "hours_left": {
            "$divide": [
                { "$subtract": ["$pickup_deadline", "$$NOW"] },
                3600000    # milliseconds → hours
            ]
        }
    }},
    { "$sort": { "hours_left": 1 } }
]
""")
            _explain(
                "**$$NOW** is a MongoDB system variable that returns the current server time — "
                "useful for computing time differences inside the pipeline without passing "
                "`datetime.now()` from Python. "
                "`$subtract` on two Date values returns the difference in **milliseconds**, "
                "so dividing by 3,600,000 converts to hours. "
                "The `available` field is computed inline using `$subtract` on numeric fields. "
                "Projecting `_id: 0` and only needed fields reduces network transfer and is "
                "good practice when not all fields are needed by the caller."
            )
            if st.button("▶ Run C3", key="c3"):
                pipeline = [
                    {"$match": {"status": "available",
                                "pickup_deadline": {"$gt": _now()}}},
                    {"$project": {
                        "_id": 0, "title": 1, "category": 1, "unit": 1,
                        "pickup_location": 1,
                        "available": {"$subtract": ["$quantity", "$claimed_quantity"]},
                        "hours_left": {"$round": [
                            {"$divide": [
                                {"$subtract": ["$pickup_deadline", "$$NOW"]},
                                3600000
                            ]}, 1
                        ]},
                    }},
                    {"$sort": {"hours_left": 1}},
                ]
                _show_result(list(db.food_listings.aggregate(pipeline)),
                             "Active listings with computed hours left")

        # ── C4. Top donors by rescue quantity ─────────────────────────────────
        with st.expander("C4 — Top 5 donors by rescued quantity ($group · $sort · $limit)"):
            _code("""\
# Leaderboard: top 5 donors ranked by total quantity rescued
pipeline = [
    { "$group": {
        "_id":           "$donor_id",
        "total_rescued": { "$sum": "$rescued_quantity" },
        "rescue_count":  { "$sum": 1 }
    }},
    { "$sort":  { "total_rescued": -1 } },
    { "$limit": 5 },                        # ← keep only top 5
    { "$lookup": {
        "from": "users", "localField": "_id",
        "foreignField": "_id", "as": "donor"
    }},
    { "$unwind": { "path": "$donor", "preserveNullAndEmptyArrays": True } },
    { "$project": {
        "_id": 0,
        "rank":          { "$literal": "—" },   # placeholder, filled in Python
        "donor_name":    { "$ifNull": ["$donor.name", "Unknown"] },
        "total_rescued": { "$round": ["$total_rescued", 2] },
        "rescue_count":  1
    }}
]
""")
            _explain(
                "Placing `$limit` **after** `$sort` but **before** `$lookup` is a critical "
                "performance pattern. If we did `$lookup` first and then limited, we would join "
                "ALL donors before discarding most of them. By limiting to 5 first, we only "
                "perform 5 lookups. Always push `$match`, `$sort`, and `$limit` as early as "
                "possible in the pipeline to reduce the document stream for later stages."
            )
            if st.button("▶ Run C4", key="c4"):
                pipeline = [
                    {"$group": {"_id": "$donor_id",
                                "total_rescued": {"$sum": "$rescued_quantity"},
                                "rescue_count":  {"$sum": 1}}},
                    {"$sort":  {"total_rescued": -1}},
                    {"$limit": 5},
                    {"$lookup": {"from": "users", "localField": "_id",
                                 "foreignField": "_id", "as": "donor"}},
                    {"$unwind": {"path": "$donor", "preserveNullAndEmptyArrays": True}},
                    {"$project": {"_id": 0,
                                  "donor_name":    {"$ifNull": ["$donor.name", "Unknown"]},
                                  "total_rescued": {"$round": ["$total_rescued", 2]},
                                  "rescue_count":  1}},
                ]
                data = list(db.rescue_records.aggregate(pipeline))
                for i, d in enumerate(data, 1):
                    d["rank"] = f"#{i}"
                _show_result(data, "Top 5 donors")

        # ── C5. $regex text search ─────────────────────────────────────────────
        with st.expander("C5 — Partial text search with $regex"):
            search_term = st.text_input("Search food titles for:", value="rice", key="c5_term")
            _code(f"""\
# Case-insensitive partial text search across title and description
db.food_listings.find({{
    "$or": [
        {{ "title":       {{ "$regex": "{search_term}", "$options": "i" }} }},
        {{ "description": {{ "$regex": "{search_term}", "$options": "i" }} }}
    ]
}}, {{ "title": 1, "category": 1, "status": 1, "pickup_location": 1 }})
""")
            _explain(
                "**$or** is a logical operator that matches documents satisfying **any** of its "
                "conditions (like SQL `OR`). `$and` is the equivalent for 'all conditions must match'. "
                "`$regex` with `$options: 'i'` does a case-insensitive substring search. "
                "For production full-text search, MongoDB Atlas Search (Lucene-based) is more "
                "powerful, but `$regex` is simple and works on any MongoDB instance without "
                "special configuration — suitable for this academic project."
            )
            if st.button("▶ Run C5", key="c5"):
                docs = list(db.food_listings.find(
                    {"$or": [
                        {"title":       {"$regex": search_term, "$options": "i"}},
                        {"description": {"$regex": search_term, "$options": "i"}},
                    ]},
                    {"title": 1, "category": 1, "status": 1, "pickup_location": 1},
                ))
                _show_result(docs, f"Listings matching '{search_term}'")

        # ── C6. Compound index query ───────────────────────────────────────────
        with st.expander("C6 — Compound index query: status + deadline together"):
            _code("""\
# This query is designed to use the compound index:
# db.food_listings.create_index([("status", ASC), ("pickup_deadline", ASC)])
# defined in database.py as "listings_status_deadline"

import pymongo
db.food_listings.find(
    {
        "status": "available",
        "pickup_deadline": { "$gt": datetime.now(timezone.utc) }
    }
).sort("pickup_deadline", 1).explain("executionStats")
# ↑ .explain() shows which index MongoDB chose — look for "IXSCAN" not "COLLSCAN"
""")
            _explain(
                "A **compound index** on `(status, pickup_deadline)` serves queries that filter "
                "on status AND sort/filter on deadline — far faster than two separate single-field "
                "indexes because MongoDB can satisfy both conditions in one index scan. "
                "`explain('executionStats')` is the MongoDB profiling tool — "
                "`IXSCAN` means an index scan was used (fast); `COLLSCAN` means a full "
                "collection scan (slow for large collections). "
                "Below we show the explain output so you can verify the index is being used."
            )
            if st.button("▶ Run C6 — Show explain plan", key="c6"):
                explain = db.food_listings.find(
                    {"status": "available",
                     "pickup_deadline": {"$gt": _now()}}
                ).sort("pickup_deadline", 1).explain("executionStats")

                stage = explain.get("queryPlanner", {}).get("winningPlan", {})
                # Walk to find the stage name
                def _find_stage(plan, depth=0):
                    name = plan.get("stage", "?")
                    child = plan.get("inputStage") or plan.get("inputStages", [{}])[0]
                    if depth < 5 and child:
                        return f"{name} → {_find_stage(child, depth+1)}"
                    return name

                plan_str = _find_stage(stage)
                exec_stats = explain.get("executionStats", {})
                nReturned  = exec_stats.get("nReturned", "?")
                totalDocsExamined = exec_stats.get("totalDocsExamined", "?")
                totalKeysExamined = exec_stats.get("totalKeysExamined", "?")

                if "IXSCAN" in plan_str:
                    st.success(f"✅ Index used!  Plan: `{plan_str}`")
                else:
                    st.warning(f"⚠️ No index hit.  Plan: `{plan_str}`")

                st.markdown(f"""
| Metric | Value |
|---|---|
| Execution plan | `{plan_str}` |
| Documents returned | {nReturned} |
| Documents examined | {totalDocsExamined} |
| Index keys examined | {totalKeysExamined} |
""")
                with st.expander("Full explain output (JSON)"):
                    st.json(json.loads(bson_dumps(explain)))
