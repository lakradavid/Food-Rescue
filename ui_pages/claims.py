"""
pages/claims.py
---------------
Claims and pickup management page.

Recipients/volunteers can:
  - Claim available food listings
  - View their claims
  - Confirm / complete / cancel claims

Donors can:
  - View claims on their listings
  - Confirm and complete pickups
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import timezone

from database import get_db
from services.claim_service import (
    claim_food,
    confirm_claim,
    complete_claim,
    cancel_claim,
    fetch_all_claims_detailed,
    claim_status_summary,
)
from services.listing_service import (
    fetch_active_listings,
    fetch_listing,
    sweep_expired_listings,
    available_quantity,
)
from services.user_service import fetch_recipients_and_volunteers, fetch_donors


STATUS_COLORS = {
    "pending":   "🟡",
    "confirmed": "🔵",
    "completed": "✅",
    "cancelled": "❌",
}


def _fmt_dt(dt):
    if dt is None:
        return "—"
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d %b %Y, %H:%M")


def render():
    st.title("🤝 Claims & Pickup Management")
    st.caption("Claim food, track pickups, and manage rescue operations.")

    db = get_db()
    sweep_expired_listings(db)

    tab_claim, tab_manage, tab_all = st.tabs([
        "🛒 Claim Food", "📋 My Claims", "🗂️ All Claims (Admin)"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 – Claim Food
    # ══════════════════════════════════════════════════════════════════════════
    with tab_claim:
        st.subheader("Claim Available Food")

        recipients = fetch_recipients_and_volunteers(db)
        if not recipients:
            st.warning("No recipients or volunteers registered yet.")
        else:
            rec_map = {f"{u['name']} ({u['role']}) — {u['email']}": str(u["_id"]) for u in recipients}
            rec_label = st.selectbox("Claiming as:", list(rec_map.keys()), key="rec_sel")
            claimant_id = rec_map[rec_label]

            active = fetch_active_listings(db)
            if not active:
                st.info("No food available right now. Check back later.")
            else:
                listing_map = {
                    f"{l['title']} | {available_quantity(l):.1f} {l['unit']} | {l['pickup_location']}": l
                    for l in active
                }
                chosen_label = st.selectbox("Select food listing:", list(listing_map.keys()), key="listing_sel")
                chosen = listing_map[chosen_label]
                avail  = available_quantity(chosen)

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Category:** {chosen.get('category', '—')}")
                    st.markdown(f"**Location:** {chosen.get('pickup_location', '—')}")
                    st.markdown(f"**Deadline:** {_fmt_dt(chosen.get('pickup_deadline'))}")
                with col2:
                    st.markdown(f"**Available:** {avail:.1f} {chosen.get('unit', '')}")
                    allergens = chosen.get("allergens", [])
                    if allergens:
                        st.warning(f"⚠️ Allergens: {', '.join(allergens)}")

                claim_qty = st.number_input(
                    f"Quantity to claim ({chosen.get('unit', '')})",
                    min_value=0.01,
                    max_value=float(avail),
                    value=min(1.0, float(avail)),
                    step=0.5,
                    key="claim_qty",
                )
                notes = st.text_input("Notes (optional)", key="claim_notes",
                                      placeholder="e.g. Will pick up at 3 PM")

                st.caption("⚠️ You are responsible for safe collection and handling of the food.")

                if st.button("✅ Submit Claim", type="primary"):
                    form_data = {
                        "listing_id":       str(chosen["_id"]),
                        "claimant_id":      claimant_id,
                        "claimed_quantity": claim_qty,
                        "notes":            notes,
                    }
                    ok, result = claim_food(db, form_data)
                    if ok:
                        st.success(f"✅ Claim submitted! Claim ID: {result}")
                        st.rerun()
                    else:
                        st.error(f"Claim failed:\n{result}")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 – My Claims
    # ══════════════════════════════════════════════════════════════════════════
    with tab_manage:
        st.subheader("Manage Your Claims")

        recipients = fetch_recipients_and_volunteers(db)
        if not recipients:
            st.warning("No recipients or volunteers registered.")
        else:
            rec_map2 = {f"{u['name']} ({u['role']})": str(u["_id"]) for u in recipients}
            rec_label2 = st.selectbox("View claims for:", list(rec_map2.keys()), key="my_rec_sel")
            my_uid = rec_map2[rec_label2]

            my_claims = fetch_all_claims_detailed(db, claimant_id=my_uid)
            if not my_claims:
                st.info("No claims found for this user.")
            else:
                for c in my_claims:
                    badge  = STATUS_COLORS.get(c.get("status", ""), "")
                    header = (
                        f"{badge} {c.get('status', '').upper()} · "
                        f"**{c.get('listing_title', 'Unknown')}** · "
                        f"{c.get('claimed_quantity', 0)} {c.get('unit', '')} · "
                        f"📍 {c.get('pickup_location', '—')}"
                    )
                    with st.expander(header):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Category:** {c.get('listing_category', '—')}")
                            st.markdown(f"**Claimed:** {c.get('claimed_quantity', 0)} {c.get('unit', '')}")
                            st.markdown(f"**Deadline:** {_fmt_dt(c.get('pickup_deadline'))}")
                        with col2:
                            st.markdown(f"**Status:** {c.get('status', '—').capitalize()}")
                            st.markdown(f"**Claimed at:** {_fmt_dt(c.get('created_at'))}")
                            if c.get("notes"):
                                st.markdown(f"**Notes:** {c['notes']}")

                        claim_id = str(c["_id"])
                        status   = c.get("status")

                        # Action buttons based on current status
                        if status == "pending":
                            col_a, col_b = st.columns(2)
                            with col_a:
                                if st.button("🔵 Confirm Pickup", key=f"conf_{claim_id}"):
                                    ok, msg = confirm_claim(db, claim_id)
                                    st.success(msg) if ok else st.error(msg)
                                    st.rerun()
                            with col_b:
                                if st.button("❌ Cancel Claim", key=f"canc_{claim_id}"):
                                    ok, msg = cancel_claim(db, claim_id)
                                    st.success(msg) if ok else st.error(msg)
                                    st.rerun()

                        elif status == "confirmed":
                            col_a, col_b = st.columns(2)
                            with col_a:
                                if st.button("✅ Mark Collected", key=f"comp_{claim_id}"):
                                    ok, msg = complete_claim(db, claim_id)
                                    st.success("Rescue recorded! " + msg) if ok else st.error(msg)
                                    st.rerun()
                            with col_b:
                                if st.button("❌ Cancel Claim", key=f"canc2_{claim_id}"):
                                    ok, msg = cancel_claim(db, claim_id)
                                    st.success(msg) if ok else st.error(msg)
                                    st.rerun()

                        elif status == "completed":
                            st.success("✅ This rescue is complete and recorded.")
                        elif status == "cancelled":
                            st.error("❌ This claim was cancelled.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 – All Claims (Admin view)
    # ══════════════════════════════════════════════════════════════════════════
    with tab_all:
        st.subheader("All Claims — Overview")

        # Summary metrics
        stats = claim_status_summary(db)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("⏳ Pending",   stats.get("pending",   0))
        c2.metric("🔵 Confirmed", stats.get("confirmed", 0))
        c3.metric("✅ Completed", stats.get("completed", 0))
        c4.metric("❌ Cancelled", stats.get("cancelled", 0))

        st.divider()

        all_claims = fetch_all_claims_detailed(db)
        if not all_claims:
            st.info("No claims in the system yet.")
        else:
            rows = []
            for c in all_claims:
                rows.append({
                    "Status":    STATUS_COLORS.get(c.get("status", ""), "") + " " + c.get("status", "").capitalize(),
                    "Food":      c.get("listing_title", "—"),
                    "Category":  c.get("listing_category", "—"),
                    "Qty":       f"{c.get('claimed_quantity', 0)} {c.get('unit', '')}",
                    "Claimant":  c.get("claimant_name", "—"),
                    "Role":      c.get("claimant_role", "—"),
                    "Location":  c.get("pickup_location", "—"),
                    "Deadline":  _fmt_dt(c.get("pickup_deadline")),
                    "Claimed At":_fmt_dt(c.get("created_at")),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            # Admin action: complete or cancel any pending/confirmed claim
            st.divider()
            st.subheader("Admin Actions")
            actionable = [c for c in all_claims if c.get("status") in ("pending", "confirmed")]
            if not actionable:
                st.info("No actionable (pending/confirmed) claims.")
            else:
                act_map = {
                    f"{c.get('listing_title', '?')} → {c.get('claimant_name', '?')} [{c.get('status')}]": c
                    for c in actionable
                }
                act_label = st.selectbox("Select claim:", list(act_map.keys()), key="admin_claim_sel")
                act_claim = act_map[act_label]
                act_id    = str(act_claim["_id"])

                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if act_claim.get("status") == "pending":
                        if st.button("🔵 Confirm", key="admin_confirm"):
                            ok, msg = confirm_claim(db, act_id)
                            st.success(msg) if ok else st.error(msg)
                            st.rerun()
                with col_b:
                    if act_claim.get("status") == "confirmed":
                        if st.button("✅ Complete & Record Rescue", key="admin_complete"):
                            ok, msg = complete_claim(db, act_id)
                            st.success("Rescue recorded. " + msg) if ok else st.error(msg)
                            st.rerun()
                with col_c:
                    if st.button("❌ Cancel", key="admin_cancel"):
                        ok, msg = cancel_claim(db, act_id)
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()
