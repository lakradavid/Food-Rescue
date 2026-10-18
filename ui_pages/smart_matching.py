"""
pages/smart_matching.py
-----------------------
Smart Food Matching recommendations page.

Explains the scoring algorithm, takes user preferences, and displays
ranked listings with plain-English explanations for each recommendation.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from database import get_db
from services.matching_service import get_matched_listings
from services.listing_service import sweep_expired_listings
from config import FOOD_CATEGORIES


def _fmt_dt(dt):
    if dt is None:
        return "—"
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d %b %Y, %H:%M")


def render():
    st.title("🤖 Smart Food Matching")
    st.caption("Rule-based recommendations that prioritise food matching your preferences and nearing their deadline.")

    db = get_db()
    sweep_expired_listings(db)

    # ── Algorithm explainer ───────────────────────────────────────────────────
    with st.expander("ℹ️ How does the matching algorithm work?"):
        st.markdown("""
        **Scoring (out of 100 points)**

        | Criterion | Points |
        |---|---|
        | Category matches your preference | +40 |
        | Location keyword matches pickup location | +30 |
        | Urgency: deadline < 2 h | +30 |
        | Urgency: deadline 2–6 h | +20 |
        | Urgency: deadline 6–12 h | +10 |
        | Urgency: deadline > 12 h | +5 |

        When no preference is given, partial points are awarded so all
        available listings still appear.

        **Tie-breaking:** Equal-score listings are sorted by earliest
        deadline first to minimise food waste.

        This is a deterministic, rule-based algorithm — no machine learning,
        no external APIs, fully explainable.
        """)

    st.divider()

    # ── Preference inputs ─────────────────────────────────────────────────────
    st.subheader("🎯 Set Your Preferences")
    col1, col2 = st.columns(2)
    with col1:
        pref_category = st.selectbox(
            "Preferred food category",
            ["Any"] + FOOD_CATEGORIES,
        )
    with col2:
        pref_location = st.text_input(
            "Your location / area keyword",
            placeholder="e.g. LPU, Phagwara, Jalandhar",
        )

    top_n = st.slider("Number of recommendations", min_value=3, max_value=20, value=8)

    if st.button("🔍 Find Matches", type="primary"):
        cat = None if pref_category == "Any" else pref_category
        loc = pref_location.strip() or None

        with st.spinner("Scoring listings…"):
            results = get_matched_listings(db, preferred_category=cat,
                                           preferred_location=loc, top_n=top_n)

        if not results:
            st.warning("No available listings found. Check back later or broaden your preferences.")
            return

        st.success(f"Found **{len(results)}** recommendation(s).")
        st.divider()

        # ── Result cards ──────────────────────────────────────────────────────
        for rank, item in enumerate(results, start=1):
            score     = item.get("match_score", 0)
            avail     = item.get("available_qty", 0)
            hours     = item.get("hours_left", 0)
            allergens = item.get("allergens", [])

            # Score colour
            if score >= 80:
                score_badge = f"🟢 {score}/100"
            elif score >= 50:
                score_badge = f"🟡 {score}/100"
            else:
                score_badge = f"🔴 {score}/100"

            header = (
                f"#{rank} · **{item.get('title', 'Untitled')}** · "
                f"{score_badge} · {avail} {item.get('unit', '')} · ⏱ {hours}h left"
            )

            with st.expander(header, expanded=(rank <= 3)):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Category:** {item.get('category', '—')}")
                    st.markdown(f"**Location:** {item.get('pickup_location', '—')}")
                    st.markdown(f"**Deadline:** {_fmt_dt(item.get('pickup_deadline'))}")
                with col2:
                    st.markdown(f"**Total Qty:** {item.get('quantity', 0)} {item.get('unit', '')}")
                    st.markdown(f"**Available:** {avail} {item.get('unit', '')}")
                    st.markdown(f"**Match score:** {score}/100")

                st.info(f"💡 {item.get('explanation', '')}")

                if allergens:
                    st.warning(f"⚠️ Allergens: {', '.join(allergens)}")

                desc = item.get("description")
                if desc:
                    st.caption(f"📝 {desc}")

                st.caption("⚠️ Food safety is the donor's responsibility. Verify condition on pickup.")

        # ── Compact table view ─────────────────────────────────────────────────
        st.divider()
        if st.checkbox("Show as table"):
            rows = [
                {
                    "Rank":      rank,
                    "Title":     r.get("title", "—"),
                    "Category":  r.get("category", "—"),
                    "Score":     r.get("match_score", 0),
                    "Available": f"{r.get('available_qty', 0)} {r.get('unit', '')}",
                    "Hours Left":r.get("hours_left", 0),
                    "Location":  r.get("pickup_location", "—"),
                    "Deadline":  _fmt_dt(r.get("pickup_deadline")),
                }
                for rank, r in enumerate(results, 1)
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("Set your preferences above and click **Find Matches** to get recommendations.")
