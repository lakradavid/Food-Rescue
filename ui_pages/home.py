"""
ui_pages/home.py
----------------
Home dashboard – professional redesign.
Hero banner · KPI cards · mini charts · urgency alerts · recent rescues.
All data from MongoDB — nothing hardcoded.
"""

from __future__ import annotations

from datetime import timezone

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio

from database import get_db
from analytics.pipelines import get_dashboard_summary, pipeline_rescue_trends, pipeline_category_analysis
from repositories.rescue_repo import get_recent_rescues
from services.listing_service import sweep_expired_listings
from services.matching_service import get_urgency_alerts
from config import KG_TO_MEALS_ESTIMATE

# Force all Plotly charts to use a white background with dark text
pio.templates["foodrescue"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="#000000",
        plot_bgcolor="#000000",
        font=dict(color="#1f2937", family="Inter, sans-serif"),
        title=dict(font=dict(color="#1a3c2e")),
        xaxis=dict(tickfont=dict(color="#374151"), gridcolor="#f3f4f6", linecolor="#e5e7eb"),
        yaxis=dict(tickfont=dict(color="#374151"), gridcolor="#f3f4f6", linecolor="#e5e7eb"),
        coloraxis=dict(colorbar=dict(tickfont=dict(color="#374151"))),
    )
)
pio.templates.default = "plotly+foodrescue"


def _fmt_dt(dt):
    if dt is None:
        return "—"
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d %b %Y, %H:%M")


def _kpi(col, value, label, sub="", color="#2e7d52"):
    col.markdown(f"""
    <div class="kpi-card" style="border-top-color:{color};">
        <div class="kpi-value">{value}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


def render():
    db = get_db()

    # Sweep expired listings silently
    expired_now = sweep_expired_listings(db)
    if expired_now:
        st.toast(f"⏰ {expired_now} listing(s) just marked expired.", icon="⏰")

    # ── Load data ─────────────────────────────────────────────────────────────
    with st.spinner("Loading dashboard…"):
        summary  = get_dashboard_summary(db)
        trends   = pipeline_rescue_trends(db, group_by="day")
        cat_data = pipeline_category_analysis(db)

    # ══════════════════════════════════════════════════════════════════════════
    #  HERO BANNER
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(f"""
    <div class="hero-banner">
        <h1>🥗 FoodRescue</h1>
        <p>Smart Food Waste Rescue &amp; Analytics System &nbsp;·&nbsp;
           <span style="color:#7dffb0; font-weight:600;">
               {summary['active_listings']} active listings
           </span> &nbsp;·&nbsp;
           <span style="color:#7dffb0; font-weight:600;">
               {summary['completed_rescues']} rescues completed
           </span>
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    #  ROW 1 — PRIMARY KPIs
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-header">📊 Live Metrics</div>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    _kpi(c1, summary["active_listings"],   "Active Listings",    "status: available",  "#2e7d52")
    _kpi(c2, summary["completed_rescues"], "Rescues Completed",  "all time",           "#1565c0")
    _kpi(c3, f"{summary['total_rescued_kg']:.1f} kg", "Food Rescued", "from rescue records", "#6a1b9a")
    _kpi(c4, summary["pending_claims"],    "Pending Claims",     "awaiting action",    "#e65100")
    _kpi(c5, f"{summary['completion_pct']}%", "Success Rate",   "completed / closed", "#2e7d52")

    st.markdown("<br>", unsafe_allow_html=True)

    c6, c7, c8, c9, c10 = st.columns(5)
    _kpi(c6,  summary["total_listings"],  "Total Listings",     "ever created",       "#37474f")
    _kpi(c7,  summary["expired_listings"],"Expired Listings",   "missed deadline",    "#c62828")
    _kpi(c8,  summary["cancelled_claims"],"Cancelled Claims",   "not rescued",        "#c62828")
    _kpi(c9,  summary["total_users"],     "Registered Users",   "donors + recipients",  "#00695c")
    _kpi(c10, f"~{summary['estimated_meals']:,}", "Est. Meals Rescued",
         f"{KG_TO_MEALS_ESTIMATE} meals/kg · estimate", "#6a1b9a")

    st.markdown("<br>", unsafe_allow_html=True)

    # Meals estimate disclaimer
    st.markdown(f"""
    <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px;
                padding:12px 18px; font-size:0.82rem; color:#166534;">
        📌 <b>Estimate note:</b> Meal count uses a conversion of
        <b>{KG_TO_MEALS_ESTIMATE} meals per kg</b> rescued.
        Only kg-unit rescue records are counted. This is an estimate — not a verified figure.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    #  ROW 2 — CHARTS (side by side)
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-header">📈 Visual Overview</div>', unsafe_allow_html=True)

    chart_left, chart_right = st.columns(2)

    # ── Rescue trend sparkline ────────────────────────────────────────────────
    with chart_left:
        if trends:
            df_t = pd.DataFrame(trends)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_t["period"], y=df_t["rescue_count"],
                mode="lines+markers",
                line=dict(color="#2e7d52", width=2.5, shape="spline"),
                marker=dict(size=6, color="#2e7d52"),
                fill="tozeroy",
                fillcolor="rgba(46,125,82,0.08)",
                name="Rescues",
            ))
            fig.update_layout(
                title=dict(text="Daily Rescue Activity", font=dict(size=14, color="#7dffb0")),
                height=260,
                margin=dict(l=10, r=10, t=40, b=10),
                paper_bgcolor="#000000",
                plot_bgcolor="#000000",
                font=dict(color="#ffffff"),
                xaxis=dict(showgrid=False, tickfont=dict(size=10, color="#aaaaaa")),
                yaxis=dict(showgrid=True, gridcolor="#222222", tickfont=dict(size=10, color="#aaaaaa")),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No rescue trend data yet. Complete some claims first.")

    # ── Category donut ────────────────────────────────────────────────────────
    with chart_right:
        if cat_data:
            df_c = pd.DataFrame(cat_data).head(6)
            fig2 = go.Figure(go.Pie(
                labels=df_c["category"],
                values=df_c["listing_count"],
                hole=0.52,
                marker=dict(colors=[
                    "#2e7d52","#1565c0","#6a1b9a","#e65100",
                    "#00695c","#c62828","#37474f","#f9a825"
                ]),
                textinfo="label+percent",
                textfont=dict(size=11, color="#ffffff"),
            ))
            fig2.update_layout(
                title=dict(text="Listings by Category", font=dict(size=14, color="#7dffb0")),
                height=260,
                margin=dict(l=10, r=10, t=40, b=10),
                paper_bgcolor="#000000",
                font=dict(color="#ffffff"),
                showlegend=False,
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No listing data yet.")

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    #  ROW 3 — CLAIM STATUS BAR + RESCUED BY UNIT
    # ══════════════════════════════════════════════════════════════════════════
    bar_left, bar_right = st.columns(2)

    with bar_left:
        st.markdown('<div class="section-header">🎯 Claim Status Breakdown</div>',
                    unsafe_allow_html=True)
        statuses = {
            "Completed":  (summary["completed_rescues"], "#2e7d52"),
            "Pending":    (summary["pending_claims"],    "#f59e0b"),
            "Cancelled":  (summary["cancelled_claims"],  "#ef4444"),
        }
        for label, (val, color) in statuses.items():
            total = max(1, sum(v for v, _ in statuses.values()))
            pct   = val / total * 100
            st.markdown(f"""
            <div style="margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between;
                            font-size:0.82rem; font-weight:600; margin-bottom:4px;
                            color:#374151;">
                    <span class="claim-label" style="color:#374151 !important;">{label}</span>
                    <span class="claim-value" style="color:{color} !important;">{val}</span>
                </div>
                <div style="background:#f3f4f6; border-radius:6px; height:8px;">
                    <div style="background:{color}; width:{pct:.1f}%;
                                height:8px; border-radius:6px;
                                transition: width 0.4s ease;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with bar_right:
        st.markdown('<div class="section-header">📦 Food Rescued by Unit</div>',
                    unsafe_allow_html=True)
        rescued_totals = summary.get("rescued_totals", [])
        if rescued_totals:
            df_r = pd.DataFrame(rescued_totals)
            fig3 = px.bar(
                df_r, x="total_rescued", y="unit",
                orientation="h",
                text="total_rescued",
                color="total_rescued",
                color_continuous_scale=[[0, "#d1fae5"], [1, "#065f46"]],
            )
            fig3.update_traces(texttemplate="%{text:.1f}", textposition="outside",
                               textfont=dict(color="#ffffff"))
            fig3.update_layout(
                height=200,
                margin=dict(l=0, r=30, t=10, b=10),
                paper_bgcolor="#000000",
                plot_bgcolor="#000000",
                font=dict(color="#ffffff"),
                xaxis=dict(showgrid=False, visible=False),
                yaxis=dict(showgrid=False, tickfont=dict(size=11, color="#aaaaaa")),
                coloraxis_showscale=False,
                showlegend=False,
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No rescue records yet.")

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    #  ROW 4 — URGENCY ALERTS
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-header">🚨 Urgent Pickups — Deadline Within 3 Hours</div>',
                unsafe_allow_html=True)

    alerts = get_urgency_alerts(db, hours_threshold=3.0)
    if alerts:
        for a in alerts:
            avail = max(0.0, float(a.get("quantity", 0)) - float(a.get("claimed_quantity", 0)))
            hrs   = a.get("hours_left", 0)
            color = "#ef4444" if hrs < 1 else "#f59e0b"
            st.markdown(f"""
            <div class="urgency-card" style="border-left-color:{color};">
                <b style="color:{color};">⏱ {hrs}h left</b> &nbsp;|&nbsp;
                <b>{a.get('title','')}</b> &nbsp;|&nbsp;
                {avail:.1f} {a.get('unit','')} available &nbsp;|&nbsp;
                📍 {a.get('pickup_location','—')}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px;
                    padding:14px 18px; color:#166534; font-weight:500;">
            ✅ No urgent listings right now. All active pickups have comfortable deadlines.
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    #  ROW 5 — RECENT RESCUES TABLE
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown('<div class="section-header">🕐 Recent Rescues</div>', unsafe_allow_html=True)

    recent = get_recent_rescues(db, limit=8)
    if recent:
        rows = [{
            "🍱 Food":      r.get("food_title", "—"),
            "Category":     r.get("category", "—"),
            "Qty Rescued":  f"{r.get('rescued_quantity', 0)} {r.get('unit', '')}",
            "Donor":        r.get("donor_name", "—"),
            "Recipient":    r.get("recipient_name", "—"),
            "📍 Location":  r.get("pickup_location", "—"),
            "🕐 When":      _fmt_dt(r.get("rescued_at")),
        } for r in recent]
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.markdown("""
        <div style="background:#fffbeb; border:1px solid #fde68a; border-radius:10px;
                    padding:14px 18px; color:#92400e;">
            No rescue records yet. Complete a claim to see results here.
        </div>
        """, unsafe_allow_html=True)

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:10px;
                padding:12px 18px; margin-top:24px; font-size:0.78rem; color:#6b7280;">
        ⚠️ <b>Food Safety Reminder:</b> Food providers are solely responsible for ensuring
        food safety, correct storage temperatures, allergen labelling, and compliance with
        applicable local food handling regulations.
        FoodRescue does not certify any food as safe for consumption.
    </div>
    """, unsafe_allow_html=True)
