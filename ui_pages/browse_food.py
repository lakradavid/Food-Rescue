"""
pages/browse_food.py
--------------------
Public browse page – search and filter available surplus food listings.
All data comes from MongoDB. Expired listings are hidden from results.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from database import get_db
from services.listing_service import fetch_listings_for_display, sweep_expired_listings
from config import FOOD_CATEGORIES


STATUS_BADGE = {
    "available": "🟢 Available",
    "reserved":  "🟡 Reserved",
    "rescued":   "✅ Rescued",
    "expired":   "🔴 Expired",
}


def _fmt_dt(dt):
    if dt is None:
        return "—"
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d %b %Y, %H:%M")


def _hours_left(deadline):
    if not isinstance(deadline, datetime):
        return None
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    delta = deadline - datetime.now(timezone.utc)
    return max(0.0, delta.total_seconds() / 3600)


def render():
    st.title("🔍 Browse Surplus Food")
    st.caption("Find available food listings near you. Expired listings are hidden.")

    db = get_db()
    sweep_expired_listings(db)

    # ── Filters sidebar ───────────────────────────────────────────────────────
    st.sidebar.header("🔎 Filter Listings")
    show_status  = st.sidebar.multiselect(
        "Status", ["available", "reserved"],
        default=["available", "reserved"],
    )
    cat_options  = ["All"] + FOOD_CATEGORIES
    sel_category = st.sidebar.selectbox("Category", cat_options)
    loc_search   = st.sidebar.text_input("Location keyword", placeholder="e.g. LPU, Phagwara")
    st.sidebar.caption("Expired and rescued listings are excluded by default.")

    # ── Build query ───────────────────────────────────────────────────────────
    query: dict = {}

    if show_status:
        query["status"] = {"$in": show_status}
    else:
        query["status"] = {"$in": ["available", "reserved"]}

    # Hide expired listings regardless of filter
    query["pickup_deadline"] = {"$gt": datetime.now(timezone.utc)}

    if sel_category != "All":
        query["category"] = sel_category

    if loc_search.strip():
        query["pickup_location"] = {"$regex": loc_search.strip(), "$options": "i"}

    # ── Fetch ─────────────────────────────────────────────────────────────────
    listings = fetch_listings_for_display(db, filter_query=query)

    st.markdown(f"**{len(listings)} listing(s) found**")

    if not listings:
        st.info("No listings match your filters. Try removing some filters or check back later.")
        return

    # ── Display cards ─────────────────────────────────────────────────────────
    for l in listings:
        avail   = max(0.0, float(l.get("quantity", 0)) - float(l.get("claimed_quantity", 0)))
        hours   = _hours_left(l.get("pickup_deadline"))
        badge   = STATUS_BADGE.get(l.get("status", ""), l.get("status", ""))
        urgency = ""
        if hours is not None:
            if hours < 2:
                urgency = " 🚨 < 2h left"
            elif hours < 6:
                urgency = " ⚠️ < 6h left"

        with st.expander(
            f"{badge}  |  **{l.get('title', 'Untitled')}** — "
            f"{avail:.1f} {l.get('unit', '')} available{urgency}"
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Category:** {l.get('category', '—')}")
                st.markdown(f"**Location:** {l.get('pickup_location', '—')}")
                st.markdown(f"**Donor:** {l.get('donor_name', '—')}")
                st.markdown(f"**Listed:** {_fmt_dt(l.get('created_at'))}")
            with col2:
                st.markdown(f"**Total Qty:** {l.get('quantity', 0)} {l.get('unit', '')}")
                st.markdown(f"**Available:** {avail:.1f} {l.get('unit', '')}")
                st.markdown(f"**Prepared:** {_fmt_dt(l.get('prepared_at'))}")
                st.markdown(f"**Deadline:** {_fmt_dt(l.get('pickup_deadline'))}")
                if hours is not None:
                    st.markdown(f"**Time left:** {hours:.1f} hours")

            desc = l.get("description")
            if desc:
                st.markdown(f"**Description:** {desc}")

            allergens = l.get("allergens", [])
            if allergens:
                st.warning(f"⚠️ Allergens: {', '.join(allergens)}")
            else:
                st.caption("No allergens listed by donor.")

            st.caption(
                "ℹ️ Food safety is the donor's responsibility. "
                "Verify condition on pickup."
            )

    st.divider()

    # ── Table view toggle ──────────────────────────────────────────────────────
    if st.checkbox("Show as table"):
        rows = []
        for l in listings:
            avail = max(0.0, float(l.get("quantity", 0)) - float(l.get("claimed_quantity", 0)))
            rows.append({
                "Title":     l.get("title", "—"),
                "Category":  l.get("category", "—"),
                "Available": f"{avail:.1f} {l.get('unit', '')}",
                "Location":  l.get("pickup_location", "—"),
                "Donor":     l.get("donor_name", "—"),
                "Deadline":  _fmt_dt(l.get("pickup_deadline")),
                "Status":    STATUS_BADGE.get(l.get("status", ""), l.get("status", "")),
                "Allergens": ", ".join(l.get("allergens", [])) or "None",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
