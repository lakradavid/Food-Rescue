"""
pages/manage_listings.py
------------------------
Donor food listing management page.
Allows a donor to: create, view, edit, and delete their listings.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta

from database import get_db
from services.listing_service import (
    add_listing,
    fetch_donor_listings,
    edit_listing,
    remove_listing,
    sweep_expired_listings,
)
from services.user_service import fetch_donors
from config import FOOD_CATEGORIES, QUANTITY_UNITS


def _now():
    return datetime.now(timezone.utc)


def _fmt_dt(dt):
    if dt is None:
        return "—"
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d %b %Y %H:%M")


STATUS_COLORS = {
    "available": "🟢",
    "reserved":  "🟡",
    "rescued":   "✅",
    "expired":   "🔴",
}


def render():
    st.title("📋 Manage Food Listings")
    st.caption("Create and manage surplus food listings as a donor.")

    db = get_db()
    sweep_expired_listings(db)

    # ── Donor selector (simulates session; replace with real auth if desired) ─
    donors = fetch_donors(db)
    if not donors:
        st.warning("No donors registered yet. Add users first via User Management.")
        return

    donor_map = {f"{d['name']} ({d['email']})": str(d["_id"]) for d in donors}
    selected_label = st.selectbox("Acting as donor:", list(donor_map.keys()))
    donor_id = donor_map[selected_label]

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_view, tab_add, tab_edit, tab_delete = st.tabs([
        "📄 My Listings", "➕ Add New", "✏️ Edit Listing", "🗑️ Delete Listing"
    ])

    # ── TAB: View own listings ─────────────────────────────────────────────────
    with tab_view:
        st.subheader("Your Food Listings")
        listings = fetch_donor_listings(db, donor_id)
        if not listings:
            st.info("You have no listings yet. Use 'Add New' to create one.")
        else:
            rows = []
            for l in listings:
                avail = max(0.0, float(l.get("quantity", 0)) - float(l.get("claimed_quantity", 0)))
                rows.append({
                    "ID":       str(l["_id"]),
                    "Title":    l.get("title", "—"),
                    "Category": l.get("category", "—"),
                    "Qty":      f"{l.get('quantity', 0)} {l.get('unit', '')}",
                    "Available":f"{avail:.1f} {l.get('unit', '')}",
                    "Location": l.get("pickup_location", "—"),
                    "Deadline": _fmt_dt(l.get("pickup_deadline")),
                    "Status":   STATUS_COLORS.get(l.get("status", ""), "") + " " + l.get("status", "").capitalize(),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # ── TAB: Add new listing ───────────────────────────────────────────────────
    with tab_add:
        st.subheader("Create a New Food Listing")
        st.caption("⚠️ You are responsible for food safety. Only list food that is safe, correctly stored, and within safe consumption time.")

        with st.form("add_listing_form", clear_on_submit=True):
            title    = st.text_input("Food Name / Title *", placeholder="e.g. Dal Makhani + Rice")
            category = st.selectbox("Category *", FOOD_CATEGORIES)
            desc     = st.text_area("Description", placeholder="Brief description, cooking method, storage info…")

            col1, col2 = st.columns(2)
            with col1:
                quantity = st.number_input("Quantity *", min_value=0.01, value=5.0, step=0.5)
            with col2:
                unit = st.selectbox("Unit *", QUANTITY_UNITS)

            location = st.text_input("Pickup Location *", placeholder="e.g. LPU Campus, Block 32")

            col3, col4 = st.columns(2)
            with col3:
                prep_date = st.date_input("Preparation Date *", value=_now().date())
                prep_time = st.time_input("Preparation Time *", value=_now().time())
            with col4:
                # Default deadline: 6 hours from now
                default_deadline = _now() + timedelta(hours=6)
                dead_date = st.date_input("Safe Pickup Deadline *", value=default_deadline.date())
                dead_time = st.time_input("Deadline Time *",        value=default_deadline.time())

            allergens_input = st.text_input(
                "Allergens (comma-separated)", placeholder="e.g. gluten, dairy, nuts"
            )

            submitted = st.form_submit_button("📤 Post Listing", type="primary")

        if submitted:
            allergens = [a.strip() for a in allergens_input.split(",") if a.strip()]
            prepared_at    = datetime.combine(prep_date, prep_time).replace(tzinfo=timezone.utc)
            pickup_deadline = datetime.combine(dead_date, dead_time).replace(tzinfo=timezone.utc)

            form_data = {
                "title":           title,
                "category":        category,
                "description":     desc,
                "quantity":        quantity,
                "unit":            unit,
                "donor_id":        donor_id,
                "pickup_location": location,
                "prepared_at":     prepared_at,
                "pickup_deadline": pickup_deadline,
                "allergens":       allergens,
            }
            ok, result = add_listing(db, form_data)
            if ok:
                st.success(f"✅ Listing created! ID: {result}")
                st.rerun()
            else:
                st.error(f"Could not create listing:\n{result}")

    # ── TAB: Edit listing ──────────────────────────────────────────────────────
    with tab_edit:
        st.subheader("Edit an Existing Listing")
        listings = fetch_donor_listings(db, donor_id)
        available_to_edit = [l for l in listings if l.get("status") == "available"]

        if not available_to_edit:
            st.info("No editable (available) listings found.")
        else:
            listing_map = {f"{l['title']} [{str(l['_id'])[:8]}…]": l for l in available_to_edit}
            chosen_label = st.selectbox("Select listing to edit:", list(listing_map.keys()), key="edit_sel")
            chosen = listing_map[chosen_label]

            with st.form("edit_listing_form"):
                new_title    = st.text_input("Title",       value=chosen.get("title", ""))
                new_category = st.selectbox("Category",     FOOD_CATEGORIES,
                                            index=FOOD_CATEGORIES.index(chosen.get("category", FOOD_CATEGORIES[0])))
                new_desc     = st.text_area("Description",  value=chosen.get("description") or "")
                new_location = st.text_input("Pickup Location", value=chosen.get("pickup_location", ""))

                col1, col2 = st.columns(2)
                with col1:
                    new_qty  = st.number_input("Quantity", min_value=0.01,
                                               value=float(chosen.get("quantity", 1)))
                with col2:
                    cur_unit = chosen.get("unit", QUANTITY_UNITS[0])
                    new_unit = st.selectbox("Unit", QUANTITY_UNITS,
                                            index=QUANTITY_UNITS.index(cur_unit) if cur_unit in QUANTITY_UNITS else 0)

                save_btn = st.form_submit_button("💾 Save Changes", type="primary")

            if save_btn:
                updates = {
                    "title": new_title, "category": new_category,
                    "description": new_desc, "pickup_location": new_location,
                    "quantity": float(new_qty), "unit": new_unit,
                }
                ok, msg = edit_listing(db, str(chosen["_id"]), updates, donor_id)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"Update failed: {msg}")

    # ── TAB: Delete listing ────────────────────────────────────────────────────
    with tab_delete:
        st.subheader("Delete a Listing")
        listings = fetch_donor_listings(db, donor_id)
        deletable = [l for l in listings if l.get("status") in ("available", "expired")]

        if not deletable:
            st.info("No deletable listings. Rescued/reserved listings cannot be deleted.")
        else:
            del_map = {f"{l['title']} — {l.get('status', '')} [{str(l['_id'])[:8]}…]": l for l in deletable}
            del_label = st.selectbox("Select listing to delete:", list(del_map.keys()), key="del_sel")
            del_listing = del_map[del_label]

            st.warning(
                f"You are about to delete: **{del_listing['title']}**  \n"
                f"Status: {del_listing.get('status')} · Qty: {del_listing.get('quantity')} {del_listing.get('unit')}"
            )
            confirm = st.checkbox("I confirm I want to delete this listing permanently.")
            if st.button("🗑️ Delete", type="primary", disabled=not confirm):
                ok, msg = remove_listing(db, str(del_listing["_id"]), donor_id)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"Delete failed: {msg}")
