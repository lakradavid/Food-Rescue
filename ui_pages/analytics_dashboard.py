"""
pages/analytics_dashboard.py
-----------------------------
Analytics and reports page.
Executes all 6 aggregation pipelines and renders results as charts
and tables. All data is live from MongoDB.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from database import get_db
from analytics.pipelines import (
    pipeline_total_food_rescued,
    pipeline_category_analysis,
    pipeline_rescue_success_rate,
    pipeline_location_analysis,
    pipeline_donor_performance,
    pipeline_rescue_trends,
)
from config import KG_TO_MEALS_ESTIMATE

# Ensure all charts render with dark text on white background
pio.templates["foodrescue"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(color="#1f2937", family="Inter, sans-serif"),
        title=dict(font=dict(color="#1a3c2e")),
        xaxis=dict(tickfont=dict(color="#374151"), gridcolor="#f3f4f6", linecolor="#e5e7eb"),
        yaxis=dict(tickfont=dict(color="#374151"), gridcolor="#f3f4f6", linecolor="#e5e7eb"),
        coloraxis=dict(colorbar=dict(tickfont=dict(color="#374151"))),
    )
)
pio.templates.default = "plotly+foodrescue"


def render():
    st.title("📊 Analytics & Reports")
    st.caption("All metrics come directly from MongoDB aggregation pipelines. Nothing is hardcoded.")

    db = get_db()

    # ── Pipeline selector tabs ────────────────────────────────────────────────
    tabs = st.tabs([
        "1️⃣ Total Rescued",
        "2️⃣ Category Analysis",
        "3️⃣ Success Rate",
        "4️⃣ Location Analysis",
        "5️⃣ Donor Performance",
        "6️⃣ Rescue Trends",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # Pipeline 1 – Total Food Rescued
    # ══════════════════════════════════════════════════════════════════════════
    with tabs[0]:
        st.subheader("Pipeline 1 — Total Food Rescued")
        st.markdown("""
        **Purpose:** Calculate the total quantity of food successfully rescued,
        grouped by unit of measurement. Uses `rescue_records` only
        (completed rescues — not listings or cancelled claims).

        **Stages:** `$group` → `$sort` → `$project`
        """)

        with st.spinner("Running pipeline…"):
            data = pipeline_total_food_rescued(db)

        if not data:
            st.info("No rescue records yet. Seed data or complete some claims first.")
        else:
            df = pd.DataFrame(data)
            col1, col2 = st.columns(2)
            with col1:
                st.dataframe(
                    df.rename(columns={
                        "unit": "Unit",
                        "total_rescued": "Total Rescued",
                        "rescue_count": "# Rescues"
                    }),
                    hide_index=True, use_container_width=True
                )
            with col2:
                fig = px.bar(
                    df, x="unit", y="total_rescued",
                    title="Total Rescued by Unit",
                    labels={"unit": "Unit", "total_rescued": "Quantity Rescued"},
                    color="total_rescued",
                    color_continuous_scale="Greens",
                    text="total_rescued",
                )
                fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
                st.plotly_chart(fig, use_container_width=True)

            # Meals estimate note
            kg_row = next((r for r in data if r["unit"] == "kg"), None)
            if kg_row:
                meals = round(kg_row["total_rescued"] * KG_TO_MEALS_ESTIMATE)
                st.info(
                    f"📌 **Estimate:** {kg_row['total_rescued']:.1f} kg rescued × "
                    f"{KG_TO_MEALS_ESTIMATE} meals/kg ≈ **{meals:,} meals** "
                    f"*(conversion assumption — not a verified figure)*"
                )

    # ══════════════════════════════════════════════════════════════════════════
    # Pipeline 2 – Category Analysis
    # ══════════════════════════════════════════════════════════════════════════
    with tabs[1]:
        st.subheader("Pipeline 2 — Category Analysis")
        st.markdown("""
        **Purpose:** Identify which food categories generate the most surplus.
        Groups all listings by category, counts them, and sums quantities.

        **Stages:** `$group` → `$addFields` (remaining qty) → `$sort` → `$project`
        """)

        with st.spinner("Running pipeline…"):
            data = pipeline_category_analysis(db)

        if not data:
            st.info("No listing data available.")
        else:
            df = pd.DataFrame(data)

            fig1 = px.bar(
                df, x="category", y=["total_quantity", "total_claimed", "remaining_quantity"],
                title="Food Surplus by Category",
                labels={"value": "Quantity", "category": "Category", "variable": "Type"},
                barmode="group",
                color_discrete_map={
                    "total_quantity": "#2196F3",
                    "total_claimed": "#FF9800",
                    "remaining_quantity": "#4CAF50",
                },
            )
            st.plotly_chart(fig1, use_container_width=True)

            fig2 = px.pie(
                df, names="category", values="listing_count",
                title="Listing Distribution by Category",
                color_discrete_sequence=px.colors.qualitative.Set3,
            )
            st.plotly_chart(fig2, use_container_width=True)

            st.dataframe(
                df.rename(columns={
                    "category": "Category", "listing_count": "# Listings",
                    "total_quantity": "Total Qty", "total_claimed": "Claimed",
                    "remaining_quantity": "Remaining", "avg_quantity": "Avg Qty",
                }),
                hide_index=True, use_container_width=True
            )

    # ══════════════════════════════════════════════════════════════════════════
    # Pipeline 3 – Rescue Success Rate
    # ══════════════════════════════════════════════════════════════════════════
    with tabs[2]:
        st.subheader("Pipeline 3 — Rescue Success Rate")
        st.markdown("""
        **Purpose:** Show claim outcome distribution and calculate the
        completion percentage (completed ÷ (completed + cancelled) × 100).
        Pending/confirmed claims are in-flight and excluded from the rate.

        **Stages:** `$group` (single-group with `$cond`) → `$addFields` → `$project`
        """)

        with st.spinner("Running pipeline…"):
            stats = pipeline_rescue_success_rate(db)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("✅ Completed",  stats["completed"])
        c2.metric("❌ Cancelled",  stats["cancelled"])
        c3.metric("⏳ Pending",    stats["pending"])
        c4.metric("🔵 Confirmed",  stats["confirmed"])
        c5.metric("🎯 Success Rate", f"{stats['completion_pct']}%")

        # Donut chart
        labels = ["Completed", "Cancelled", "Pending", "Confirmed"]
        values = [
            stats["completed"], stats["cancelled"],
            stats["pending"],   stats["confirmed"],
        ]
        colors = ["#4CAF50", "#F44336", "#FF9800", "#2196F3"]
        fig = go.Figure(data=[go.Pie(
            labels=labels, values=values,
            hole=0.45,
            marker_colors=colors,
        )])
        fig.update_layout(title_text="Claim Status Distribution")
        st.plotly_chart(fig, use_container_width=True)

        # Gauge for success rate
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=stats["completion_pct"],
            title={"text": "Rescue Completion Rate (%)"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar":  {"color": "#4CAF50"},
                "steps": [
                    {"range": [0,  50],  "color": "#ffcccc"},
                    {"range": [50, 75],  "color": "#fff3cc"},
                    {"range": [75, 100], "color": "#ccffcc"},
                ],
            },
        ))
        st.plotly_chart(fig_gauge, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Pipeline 4 – Location Analysis
    # ══════════════════════════════════════════════════════════════════════════
    with tabs[3]:
        st.subheader("Pipeline 4 — Location Analysis")
        st.markdown("""
        **Purpose:** Identify geographic hotspots of surplus food and
        successful rescues. Combines data from `food_listings` and
        `rescue_records` (merged in Python for compatibility with all
        MongoDB versions, equivalent to a `$unionWith` pipeline).

        **Stages:** `$group` on both collections → Python merge → sort
        """)

        with st.spinner("Running pipeline…"):
            data = pipeline_location_analysis(db)

        if not data:
            st.info("No location data available.")
        else:
            df = pd.DataFrame(data)

            fig = px.bar(
                df.head(10), x="location",
                y=["listing_count", "rescue_count"],
                title="Listings vs Rescues by Location (Top 10)",
                labels={"value": "Count", "location": "Location", "variable": "Type"},
                barmode="group",
                color_discrete_map={"listing_count": "#2196F3", "rescue_count": "#4CAF50"},
            )
            fig.update_xaxes(tickangle=30)
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                df.rename(columns={
                    "location": "Location", "listing_count": "# Listings",
                    "total_quantity": "Total Qty Listed",
                    "rescue_count": "# Rescues", "rescued_total": "Total Rescued",
                }),
                hide_index=True, use_container_width=True
            )

    # ══════════════════════════════════════════════════════════════════════════
    # Pipeline 5 – Donor Performance
    # ══════════════════════════════════════════════════════════════════════════
    with tabs[4]:
        st.subheader("Pipeline 5 — Donor Performance")
        st.markdown("""
        **Purpose:** Rank donors by real-world impact — how much food they
        contributed to successful rescues.

        **Stages:** `$group` (on rescue_records by donor_id) → `$sort` →
        `$lookup` (join users) → `$unwind` → `$project`
        """)

        with st.spinner("Running pipeline…"):
            data = pipeline_donor_performance(db)

        if not data:
            st.info("No donor performance data yet. Complete some claims first.")
        else:
            df = pd.DataFrame(data)
            df["categories_str"] = df["categories"].apply(
                lambda c: ", ".join(c) if isinstance(c, list) else str(c)
            )

            fig = px.bar(
                df, x="donor_name", y="total_rescued",
                title="Top Donors by Total Food Rescued",
                labels={"donor_name": "Donor", "total_rescued": "Total Rescued"},
                color="rescue_events",
                color_continuous_scale="Teal",
                text="total_rescued",
            )
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            fig.update_xaxes(tickangle=20)
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(
                df[["donor_name", "donor_location", "total_rescued", "rescue_events", "categories_str"]]
                .rename(columns={
                    "donor_name": "Donor", "donor_location": "Location",
                    "total_rescued": "Total Rescued", "rescue_events": "# Rescues",
                    "categories_str": "Food Categories",
                }),
                hide_index=True, use_container_width=True
            )

    # ══════════════════════════════════════════════════════════════════════════
    # Pipeline 6 – Rescue Trends
    # ══════════════════════════════════════════════════════════════════════════
    with tabs[5]:
        st.subheader("Pipeline 6 — Rescue Trends Over Time")
        st.markdown("""
        **Purpose:** Show how rescue activity changes over time to identify
        growth trends, busy periods, or gaps.

        **Stages:** `$group` by `$dateToString` (day or month) → `$sort` → `$project`
        """)

        granularity = st.radio("Group by:", ["day", "month"], horizontal=True)

        with st.spinner("Running pipeline…"):
            data = pipeline_rescue_trends(db, group_by=granularity)

        if not data:
            st.info("No rescue records to show trends. Complete some claims first.")
        else:
            df = pd.DataFrame(data)

            fig1 = px.line(
                df, x="period", y="rescue_count",
                title=f"Rescue Events per {granularity.capitalize()}",
                markers=True,
                labels={"period": "Period", "rescue_count": "Rescue Events"},
                line_shape="spline",
            )
            fig1.update_traces(line_color="#4CAF50", marker_size=8)
            st.plotly_chart(fig1, use_container_width=True)

            fig2 = px.bar(
                df, x="period", y="total_rescued",
                title=f"Total Quantity Rescued per {granularity.capitalize()}",
                labels={"period": "Period", "total_rescued": "Quantity Rescued"},
                color="total_rescued",
                color_continuous_scale="Greens",
            )
            st.plotly_chart(fig2, use_container_width=True)

            st.dataframe(
                df.rename(columns={
                    "period": "Period",
                    "rescue_count": "# Rescues",
                    "total_rescued": "Total Rescued",
                }),
                hide_index=True, use_container_width=True
            )

    st.divider()
    st.caption(
        "All metrics are computed live from MongoDB aggregation pipelines. "
        "Rescued quantities include only completed rescue records. "
        "Meal estimates use a conversion assumption of "
        f"{KG_TO_MEALS_ESTIMATE} meals per kg and are clearly labelled as estimates."
    )
