"""
api/index.py
------------
FoodRescue – FastAPI backend, Vercel-deployable via Mangum.

All business logic lives in the existing services / repositories /
analytics layers (unchanged).  This file only wires HTTP routes to those
layers and handles JSON serialisation of BSON types.

Route map
─────────
  GET  /api/health

  Users
  POST   /api/users
  GET    /api/users
  GET    /api/users/{user_id}
  PUT    /api/users/{user_id}
  DELETE /api/users/{user_id}

  Listings
  POST   /api/listings
  GET    /api/listings
  GET    /api/listings/{listing_id}
  PUT    /api/listings/{listing_id}
  DELETE /api/listings/{listing_id}
  POST   /api/listings/sweep-expired

  Claims
  POST   /api/claims
  GET    /api/claims
  GET    /api/claims/{claim_id}
  PATCH  /api/claims/{claim_id}/confirm
  PATCH  /api/claims/{claim_id}/complete
  PATCH  /api/claims/{claim_id}/cancel

  Rescue records
  GET    /api/rescues
  GET    /api/rescues/recent

  Analytics
  GET    /api/analytics/dashboard
  GET    /api/analytics/total-rescued
  GET    /api/analytics/categories
  GET    /api/analytics/success-rate
  GET    /api/analytics/locations
  GET    /api/analytics/donors
  GET    /api/analytics/trends

  Smart matching
  GET    /api/match
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from typing import Any, Optional

# ── make sure project root is on the path so existing modules resolve ─────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum
from bson import ObjectId
from pymongo.errors import ConnectionFailure

from database import get_db, init_db
from config import FOOD_CATEGORIES, QUANTITY_UNITS, LISTING_STATUSES, CLAIM_STATUSES, USER_ROLES, KG_TO_MEALS_ESTIMATE

from services.user_service import (
    register_user, fetch_user, fetch_all_users,
    edit_user, deactivate_user,
)
from services.listing_service import (
    add_listing, fetch_listings, fetch_listing,
    edit_listing, remove_listing, sweep_expired_listings,
    change_listing_status,
)
from services.claim_service import (
    claim_food, confirm_claim, complete_claim, cancel_claim,
    fetch_all_claims_detailed, fetch_claim, claim_status_summary,
)
from services.matching_service import get_matched_listings, get_urgency_alerts
from analytics.pipelines import (
    get_dashboard_summary,
    pipeline_total_food_rescued,
    pipeline_category_analysis,
    pipeline_rescue_success_rate,
    pipeline_location_analysis,
    pipeline_donor_performance,
    pipeline_rescue_trends,
)
from repositories.rescue_repo import get_recent_rescues

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="FoodRescue API",
    description="Smart Food Waste Rescue & Analytics — MongoDB + FastAPI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB init (runs once per cold start) ───────────────────────────────────────
_db_ready = False

def _get_db():
    global _db_ready
    if not _db_ready:
        try:
            init_db()
            _db_ready = True
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")
    return get_db()


# ── BSON serialiser ───────────────────────────────────────────────────────────
def _serial(obj: Any) -> Any:
    """Recursively convert BSON/datetime objects to JSON-safe types."""
    if isinstance(obj, dict):
        return {k: _serial(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serial(i) for i in obj]
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    return obj


def _ok(data: Any) -> JSONResponse:
    return JSONResponse(content=_serial(data))


# ═════════════════════════════════════════════════════════════════════════════
#  Health
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    try:
        db = _get_db()
        db.command("ping")
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(exc)})


# ═════════════════════════════════════════════════════════════════════════════
#  Config constants (for frontend dropdowns)
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/config")
def get_config():
    return _ok({
        "categories": FOOD_CATEGORIES,
        "units": QUANTITY_UNITS,
        "listing_statuses": LISTING_STATUSES,
        "claim_statuses": CLAIM_STATUSES,
        "user_roles": USER_ROLES,
        "kg_to_meals": KG_TO_MEALS_ESTIMATE,
    })


# ═════════════════════════════════════════════════════════════════════════════
#  Users
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/users", status_code=201)
def create_user_route(body: dict):
    db = _get_db()
    ok, result = register_user(db, body)
    if not ok:
        raise HTTPException(status_code=400, detail=result)
    return _ok({"id": result, "message": "User registered."})


@app.get("/api/users")
def list_users(role: Optional[str] = Query(None)):
    db = _get_db()
    users = fetch_all_users(db, role=role)
    return _ok(users)


@app.get("/api/users/{user_id}")
def get_user_route(user_id: str):
    db = _get_db()
    user = fetch_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return _ok(user)


@app.put("/api/users/{user_id}")
def update_user_route(user_id: str, body: dict):
    db = _get_db()
    ok, msg = edit_user(db, user_id, body)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _ok({"message": msg})


@app.delete("/api/users/{user_id}")
def delete_user_route(user_id: str):
    db = _get_db()
    ok, msg = deactivate_user(db, user_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _ok({"message": msg})


# ═════════════════════════════════════════════════════════════════════════════
#  Food Listings
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/listings", status_code=201)
def create_listing_route(body: dict):
    db = _get_db()
    # Parse datetime strings from JSON into datetime objects
    for field in ("prepared_at", "pickup_deadline"):
        if field in body and isinstance(body[field], str):
            try:
                dt = datetime.fromisoformat(body[field].replace("Z", "+00:00"))
                body[field] = dt
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid datetime for '{field}'.")
    ok, result = add_listing(db, body)
    if not ok:
        raise HTTPException(status_code=400, detail=result)
    return _ok({"id": result, "message": "Listing created."})


@app.get("/api/listings")
def list_listings(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    donor_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    skip: int = Query(0),
):
    db = _get_db()
    filters = {}
    if status:
        filters["status"] = status
    if category:
        filters["category"] = category
    if location:
        filters["pickup_location"] = {"$regex": location, "$options": "i"}
    listings = fetch_listings(db, filters=filters, donor_id=donor_id, limit=limit, skip=skip)
    return _ok(listings)


@app.get("/api/listings/{listing_id}")
def get_listing_route(listing_id: str):
    db = _get_db()
    listing = fetch_listing(db, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    return _ok(listing)


@app.put("/api/listings/{listing_id}")
def update_listing_route(listing_id: str, body: dict):
    db = _get_db()
    for field in ("prepared_at", "pickup_deadline"):
        if field in body and isinstance(body[field], str):
            try:
                body[field] = datetime.fromisoformat(body[field].replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid datetime for '{field}'.")
    ok, msg = edit_listing(db, listing_id, body)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _ok({"message": msg})


@app.delete("/api/listings/{listing_id}")
def delete_listing_route(listing_id: str):
    db = _get_db()
    ok, msg = remove_listing(db, listing_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _ok({"message": msg})


@app.post("/api/listings/sweep-expired")
def sweep_expired_route():
    db = _get_db()
    count = sweep_expired_listings(db)
    return _ok({"expired_count": count, "message": f"{count} listing(s) marked expired."})


# ═════════════════════════════════════════════════════════════════════════════
#  Claims
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/api/claims", status_code=201)
def create_claim_route(body: dict):
    db = _get_db()
    ok, result = claim_food(db, body)
    if not ok:
        raise HTTPException(status_code=400, detail=result)
    return _ok({"id": result, "message": "Claim created."})


@app.get("/api/claims")
def list_claims(claimant_id: Optional[str] = Query(None)):
    db = _get_db()
    claims = fetch_all_claims_detailed(db, claimant_id=claimant_id)
    return _ok(claims)


@app.get("/api/claims/{claim_id}")
def get_claim_route(claim_id: str):
    db = _get_db()
    claim = fetch_claim(db, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    return _ok(claim)


@app.patch("/api/claims/{claim_id}/confirm")
def confirm_claim_route(claim_id: str):
    db = _get_db()
    ok, msg = confirm_claim(db, claim_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _ok({"message": msg})


@app.patch("/api/claims/{claim_id}/complete")
def complete_claim_route(claim_id: str):
    db = _get_db()
    ok, msg = complete_claim(db, claim_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _ok({"message": msg})


@app.patch("/api/claims/{claim_id}/cancel")
def cancel_claim_route(claim_id: str):
    db = _get_db()
    ok, msg = cancel_claim(db, claim_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return _ok({"message": msg})


# ═════════════════════════════════════════════════════════════════════════════
#  Rescue Records
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/rescues")
def list_rescues(
    donor_id: Optional[str] = Query(None),
    recipient_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    from repositories.rescue_repo import get_all_rescue_records
    db = _get_db()
    records = get_all_rescue_records(db, donor_id=donor_id,
                                     recipient_id=recipient_id,
                                     category=category, limit=limit)
    return _ok(records)


@app.get("/api/rescues/recent")
def recent_rescues(limit: int = Query(8, le=50)):
    db = _get_db()
    records = get_recent_rescues(db, limit=limit)
    return _ok(records)


# ═════════════════════════════════════════════════════════════════════════════
#  Analytics
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/analytics/dashboard")
def analytics_dashboard():
    db = _get_db()
    summary = get_dashboard_summary(db)
    return _ok(summary)


@app.get("/api/analytics/total-rescued")
def analytics_total_rescued():
    db = _get_db()
    return _ok(pipeline_total_food_rescued(db))


@app.get("/api/analytics/categories")
def analytics_categories():
    db = _get_db()
    return _ok(pipeline_category_analysis(db))


@app.get("/api/analytics/success-rate")
def analytics_success_rate():
    db = _get_db()
    return _ok(pipeline_rescue_success_rate(db))


@app.get("/api/analytics/locations")
def analytics_locations():
    db = _get_db()
    return _ok(pipeline_location_analysis(db))


@app.get("/api/analytics/donors")
def analytics_donors():
    db = _get_db()
    return _ok(pipeline_donor_performance(db))


@app.get("/api/analytics/trends")
def analytics_trends(group_by: str = Query("day", regex="^(day|month)$")):
    db = _get_db()
    return _ok(pipeline_rescue_trends(db, group_by=group_by))


# ═════════════════════════════════════════════════════════════════════════════
#  Smart Matching
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/api/match")
def smart_match(
    category: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    top_n: int = Query(10, le=50),
):
    db = _get_db()
    prefs = {}
    if category:
        prefs["category"] = category
    if location:
        prefs["location"] = location
    results = get_matched_listings(db, preferences=prefs, top_n=top_n)
    return _ok(results)


@app.get("/api/alerts")
def urgency_alerts(hours: float = Query(3.0)):
    db = _get_db()
    alerts = get_urgency_alerts(db, hours_threshold=hours)
    return _ok(alerts)


# ═════════════════════════════════════════════════════════════════════════════
#  Mangum handler (Vercel / AWS Lambda ASGI adapter)
# ═════════════════════════════════════════════════════════════════════════════
handler = Mangum(app, lifespan="off")
