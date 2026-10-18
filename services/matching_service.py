"""
services/matching_service.py
-----------------------------
Rule-based Smart Food Matching engine.

NO machine learning, NO external APIs.

Algorithm (fully explained for viva):
──────────────────────────────────────
Given a recipient's preferences (category and/or location), the engine:

  Step 1 – Filter
    Query MongoDB for all listings where:
      • status = 'available'
      • pickup_deadline > now  (not expired)
      • claimed_quantity < quantity  (still has food left)

  Step 2 – Score
    Each listing gets a score from 0–100 based on:
      • Category match:  +40 points if category matches preference
      • Location match:  +30 points if pickup_location contains the
                         preferred location string (case-insensitive)
      • Urgency bonus:   +30 points scaled inversely to hours remaining
                         before the deadline (sooner = higher score)

  Step 3 – Sort
    Sort by score descending.  Ties broken by pickup_deadline ascending
    (earliest deadline first) to reduce waste.

  Step 4 – Explain
    Each result includes a human-readable explanation string so the UI
    can show WHY a listing was recommended.

This approach is fully transparent, deterministic, and easy to explain
in a viva without requiring ML knowledge.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pymongo.database import Database

from repositories.listing_repo import get_listings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hours_remaining(deadline: datetime) -> float:
    """Return hours until deadline. Returns 0 if already past."""
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    delta = deadline - _now()
    return max(0.0, delta.total_seconds() / 3600)


def _urgency_score(hours: float) -> float:
    """
    Convert hours remaining into a 0–30 urgency score.
    < 2 hours  → 30 (maximum urgency)
    2–6 hours  → 20
    6–12 hours → 10
    > 12 hours → 5
    """
    if hours < 2:
        return 30.0
    elif hours < 6:
        return 20.0
    elif hours < 12:
        return 10.0
    else:
        return 5.0


def _build_explanation(
    listing: dict,
    category_matched: bool,
    location_matched: bool,
    hours: float,
    score: float,
) -> str:
    """Build a plain-English explanation for why a listing was recommended."""
    reasons = []
    if category_matched:
        reasons.append(f"matches your preferred category '{listing['category']}'")
    if location_matched:
        reasons.append(f"is available near '{listing['pickup_location']}'")
    if hours < 2:
        reasons.append("⚠️ deadline is very soon (< 2 hours)")
    elif hours < 6:
        reasons.append("deadline is today (< 6 hours)")

    if not reasons:
        reasons.append("is available and has remaining quantity")

    base = f"Recommended because it {', '.join(reasons)}."
    base += f"  Score: {score:.0f}/100."
    return base


def get_matched_listings(
    db: Database,
    preferred_category: Optional[str] = None,
    preferred_location: Optional[str] = None,
    top_n: int = 10,
) -> list[dict]:
    """
    Main matching function.

    Parameters
    ----------
    preferred_category : food category the recipient wants (or None = any)
    preferred_location : location keyword the recipient is near (or None = any)
    top_n              : return at most this many recommendations

    Returns a list of listing dicts with extra keys:
        match_score   : int  (0–100)
        hours_left    : float
        available_qty : float
        explanation   : str
    """
    # ── Step 1: Fetch all available, non-expired listings ────────────────────
    candidates = get_listings(db, only_active=True, limit=500)

    if not candidates:
        return []

    # ── Step 2: Score each listing ───────────────────────────────────────────
    scored: list[dict] = []

    for listing in candidates:
        available_qty = float(listing.get("quantity", 0)) - float(listing.get("claimed_quantity", 0))
        if available_qty <= 0:
            continue  # fully claimed (shouldn't happen with only_active=True, but guard anyway)

        score = 0.0
        category_matched = False
        location_matched = False

        # Category match (+40)
        if preferred_category:
            if listing.get("category") == preferred_category:
                score += 40
                category_matched = True
        else:
            # No preference → give partial credit so listing still appears
            score += 20

        # Location match (+30)
        deadline = listing.get("pickup_deadline")
        if preferred_location:
            loc = listing.get("pickup_location", "")
            if preferred_location.lower() in loc.lower():
                score += 30
                location_matched = True
        else:
            score += 15  # neutral

        # Urgency score (+up to 30)
        hours = 0.0
        if isinstance(deadline, datetime):
            hours = _hours_remaining(deadline)
        score += _urgency_score(hours)

        explanation = _build_explanation(
            listing, category_matched, location_matched, hours, score
        )

        scored.append({
            **listing,
            "match_score":   round(score),
            "hours_left":    round(hours, 1),
            "available_qty": round(available_qty, 2),
            "explanation":   explanation,
        })

    # ── Step 3: Sort by score desc, then deadline asc ────────────────────────
    scored.sort(key=lambda x: (-x["match_score"], x.get("pickup_deadline") or datetime.max.replace(tzinfo=timezone.utc)))

    # ── Step 4: Return top N ─────────────────────────────────────────────────
    return scored[:top_n]


def get_urgency_alerts(db: Database, hours_threshold: float = 3.0) -> list[dict]:
    """
    Return all available listings whose deadline is within `hours_threshold`
    hours.  Used for the dashboard urgency banner.
    """
    all_active = get_listings(db, only_active=True, limit=500)
    alerts = []
    for listing in all_active:
        deadline = listing.get("pickup_deadline")
        if isinstance(deadline, datetime):
            hours = _hours_remaining(deadline)
            if hours <= hours_threshold:
                avail = float(listing.get("quantity", 0)) - float(listing.get("claimed_quantity", 0))
                if avail > 0:
                    alerts.append({**listing, "hours_left": round(hours, 1)})
    alerts.sort(key=lambda x: x["hours_left"])
    return alerts
