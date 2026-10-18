"""
app.py
------
FoodRescue – Main Streamlit entry point.

Run with:
    streamlit run app.py

On first run the app:
  1. Initialises the MongoDB database (creates collections + indexes).
  2. Performs a one-time expiry sweep.
  3. Renders the selected navigation page.
"""

from __future__ import annotations

import sys
import logging

import streamlit as st
from pymongo.errors import ConnectionFailure

# ── Page config must be the FIRST Streamlit call ─────────────────────────────
st.set_page_config(
    page_title="FoodRescue",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS theme ──────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* Apply font without touching colour */
html, body {
    font-family: 'Inter', sans-serif !important;
}

/* ── Page background – clean white ── */
.stApp {
    background-color: #f8fafb !important;
}

/* ── ALL body text – dark so it's always readable ── */
.stApp label,
.stApp li,
.stApp td,
.stApp th {
    color: #1f2937;
}
/* Only target plain Streamlit-generated paragraphs, not custom HTML */
.stApp > section p,
[data-testid="stVerticalBlock"] > div > div > p {
    color: #1f2937;
}

/* ── Headings ── */
.stApp h1 { color: #1a3c2e !important; font-weight: 700 !important; }
.stApp h2 { color: #1a3c2e !important; font-weight: 600 !important; }
.stApp h3 { color: #2e7d52 !important; font-weight: 600 !important; }
.stApp h4, .stApp h5 { color: #374151 !important; }

/* ── Streamlit native text – main content only ── */
[data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] li,
[data-testid="stMain"] label,
[data-testid="stMain"] p {
    color: #1f2937 !important;
}

/* ── Inline-styled elements keep their own colours ── */
/* Elements with inline style attributes inherit from their parent div's color,
   not from Streamlit's !important overrides */
[data-testid="stMarkdownContainer"] div[class],
[data-testid="stMarkdownContainer"] div[class] span,
[data-testid="stMarkdownContainer"] div[class] b,
[data-testid="stMarkdownContainer"] div[class] p {
    color: inherit;
}
/* Named component classes get explicit colours */
.section-header,
[data-testid="stMarkdownContainer"] .section-header { color: #1a3c2e !important; }
.kpi-value,
[data-testid="stMarkdownContainer"] .kpi-value      { color: #1a3c2e !important; }
.kpi-label,
[data-testid="stMarkdownContainer"] .kpi-label      { color: #6b7280 !important; }
.kpi-sub,
[data-testid="stMarkdownContainer"] .kpi-sub        { color: #9ca3af !important; }
.hero-banner,
[data-testid="stMarkdownContainer"] .hero-banner    { color: white !important; }
[data-testid="stMarkdownContainer"] .hero-banner p  { color: #b7dfc8 !important; }
[data-testid="stMarkdownContainer"] .urgency-card   { color: #1f2937 !important; }
/* Claim status bar labels */
.claim-label,
[data-testid="stMarkdownContainer"] .claim-label    { color: #374151 !important; }

/* Caption / small text */
.stApp .stCaption,
.stApp small {
    color: #6b7280 !important;
}

/* ── Sidebar – dark green, light text ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a3c2e 0%, #0f2419 100%) !important;
    border-right: 1px solid #2d5a3d !important;
}

/* Light text for EVERYTHING inside sidebar – high specificity */
[data-testid="stSidebar"] p                         { color: #d4edda !important; }
[data-testid="stSidebar"] span                       { color: #d4edda !important; }
[data-testid="stSidebar"] div                        { color: #d4edda !important; }
[data-testid="stSidebar"] label                      { color: #d4edda !important; }
[data-testid="stSidebar"] li                         { color: #d4edda !important; }
[data-testid="stSidebar"] a                          { color: #d4edda !important; }
[data-testid="stSidebar"] small                      { color: #a8d5b5 !important; }

/* Radio nav items specifically */
[data-testid="stSidebar"] [data-testid="stRadio"] label          { color: #d4edda !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label p        { color: #d4edda !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label span     { color: #d4edda !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] div            { color: #d4edda !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p  { color: #d4edda !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span { color: #d4edda !important; }

/* Selected radio item highlight */
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) span {
    color: #7dffb0 !important;
    font-weight: 600 !important;
}

[data-testid="stSidebar"] hr {
    border-color: #2d5a3d !important;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #ffffff;
    border-radius: 12px;
    padding: 16px 18px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    border-left: 4px solid #2e7d52;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(0,0,0,0.13);
}
[data-testid="stMetricLabel"] p {
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    color: #6b7280 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    color: #1a3c2e !important;
}

/* ── Dataframes ── */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: #ffffff;
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    margin-bottom: 8px;
}
/* Expander header text */
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary p {
    color: #1f2937 !important;
    font-weight: 600 !important;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #2e7d52, #1a3c2e) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 8px 20px !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #3d9966, #2e7d52) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(46,125,82,0.35) !important;
}

/* ── Alerts / info boxes ── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
}
[data-testid="stAlert"] p,
[data-testid="stAlert"] span {
    color: inherit !important;  /* let Streamlit control alert text colour */
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tab"] {
    font-weight: 600;
    font-size: 0.85rem;
    color: #374151 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #2e7d52 !important;
    border-bottom-color: #2e7d52 !important;
}

/* ── Form inputs ── */
.stSelectbox label,
.stTextInput label,
.stNumberInput label,
.stDateInput label,
.stTimeInput label,
.stTextArea label,
.stRadio label,
.stCheckbox label,
.stSlider label {
    color: #374151 !important;
    font-weight: 500 !important;
}
.stSelectbox > div > div,
.stTextInput > div > div {
    border-radius: 8px !important;
    border-color: #d1d5db !important;
    color: #1f2937 !important;
}

/* ── Divider ── */
hr { border-color: #e5e7eb !important; margin: 1.5rem 0 !important; }

/* ── Code blocks ── */
pre, code {
    color: #1f2937 !important;
    background-color: #f3f4f6 !important;
}

/* ── Custom KPI card (used in home.py) ── */
.kpi-card {
    background: white;
    border-radius: 14px;
    padding: 22px 24px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.07);
    border-top: 4px solid #2e7d52;
    text-align: center;
    height: 100%;
}
.kpi-card .kpi-value {
    font-size: 2.4rem;
    font-weight: 700;
    color: #1a3c2e !important;
    line-height: 1.1;
}
.kpi-card .kpi-label {
    font-size: 0.78rem;
    font-weight: 600;
    color: #6b7280 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 6px;
}
.kpi-card .kpi-sub {
    font-size: 0.82rem;
    color: #9ca3af !important;
    margin-top: 4px;
}

/* ── Hero banner ── */
.hero-banner {
    background: linear-gradient(135deg, #1a3c2e 0%, #2e7d52 60%, #4caf78 100%);
    border-radius: 16px;
    padding: 36px 40px;
    color: white;
    margin-bottom: 28px;
}
.hero-banner h1 {
    color: white !important;
    font-size: 2.2rem;
    margin: 0 0 8px 0;
}
.hero-banner p,
.stApp .hero-banner p,
[data-testid="stMain"] .hero-banner p,
[data-testid="stMarkdownContainer"] .hero-banner p {
    color: #b7dfc8 !important;
    font-size: 1.05rem;
    margin: 0;
}
.hero-banner span[style*="color"] {
    /* individual inline-coloured spans inside the banner keep their own colour */
    color: inherit;
}

/* ── Urgency badge ── */
.urgency-card {
    background: #fff5f5;
    border-left: 4px solid #ef4444;
    border-radius: 0 10px 10px 0;
    padding: 12px 18px;
    margin-bottom: 8px;
    color: #1f2937;
}
.urgency-card b,
.stApp .urgency-card b,
[data-testid="stMarkdownContainer"] .urgency-card b {
    color: #991b1b !important;
}

/* ── Section header ── */
.section-header {
    font-size: 1.1rem;
    font-weight: 700;
    color: #1a3c2e !important;
    padding: 6px 0 10px 0;
    border-bottom: 2px solid #e5e7eb;
    margin-bottom: 16px;
    letter-spacing: -0.01em;
}

/* ── Selectbox / radio / checkbox option text ── */
[data-testid="stSelectbox"] span,
[data-testid="stSelectbox"] div,
[data-baseweb="select"] span,
[data-baseweb="select"] div,
[data-baseweb="menu"] li,
[data-baseweb="menu"] span {
    color: #1f2937 !important;
}

/* ── Radio button labels ── */
[data-testid="stRadio"] label span,
[data-testid="stRadio"] p {
    color: #1f2937 !important;
}

/* ── Checkbox labels ── */
[data-testid="stCheckbox"] label span,
[data-testid="stCheckbox"] p {
    color: #1f2937 !important;
}

/* ── Slider label and value ── */
[data-testid="stSlider"] label,
[data-testid="stSlider"] p,
[data-testid="stSlider"] span {
    color: #1f2937 !important;
}

/* ── Number input ── */
[data-testid="stNumberInput"] label,
[data-testid="stNumberInput"] p {
    color: #1f2937 !important;
}

/* ── Textarea ── */
[data-testid="stTextArea"] label,
[data-testid="stTextArea"] p {
    color: #1f2937 !important;
}

/* ── Date / time input ── */
[data-testid="stDateInput"] label,
[data-testid="stTimeInput"] label {
    color: #1f2937 !important;
}

/* ── Subheader / caption native elements ── */
[data-testid="stSubheader"],
[data-testid="stCaptionContainer"] p {
    color: #374151 !important;
}

/* ── Toast notification ── */
[data-testid="stToast"] p {
    color: #1f2937 !important;
}

/* ── Spinner text ── */
[data-testid="stSpinner"] p {
    color: #374151 !important;
}

/* ── Tab panel content text ── */
[data-testid="stTabsContent"] p,
[data-testid="stTabsContent"] span,
[data-testid="stTabsContent"] label {
    color: #1f2937 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Database initialisation (cached so it only runs once per session) ─────────
@st.cache_resource(show_spinner="Connecting to MongoDB…")
def _init_database():
    from database import init_db
    return init_db()


def _check_db() -> bool:
    """Returns True if DB is ready; shows error and returns False otherwise."""
    try:
        _init_database()
        return True
    except ConnectionFailure as exc:
        st.error(
            "**Cannot connect to MongoDB.**\n\n"
            f"Error: `{exc}`\n\n"
            "Check that:\n"
            "- MongoDB is running (local) or your Atlas cluster is reachable.\n"
            "- `MONGO_URI` is set correctly in your `.env` file.\n"
            "- Network / firewall allows the connection."
        )
        return False
    except Exception as exc:
        st.error(f"Unexpected startup error: {exc}")
        logger.exception("Startup error")
        return False


# ── Navigation ────────────────────────────────────────────────────────────────
PAGES = {
    "🏠 Home Dashboard":          "home",
    "📋 Manage Listings":         "manage_listings",
    "🔍 Browse Food":             "browse_food",
    "🤖 Smart Matching":          "smart_matching",
    "🤝 Claims & Pickup":         "claims",
    "📊 Analytics & Reports":     "analytics_dashboard",
    "👥 User Management":         "user_management",
    "🔬 Query Explorer":          "query_explorer",
}


def main():
    # ── Sidebar navigation ────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding: 10px 0 4px 0;">
            <div style="font-size:2.8rem;">🥗</div>
            <div style="font-size:1.35rem; font-weight:700; color:#d4edda;
                        letter-spacing:-0.02em; margin-top:4px;">FoodRescue</div>
            <div style="font-size:0.75rem; color:#7fbf95; margin-top:2px;">
                Smart Food Waste Rescue System
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        selection = st.radio(
            "Navigate to:",
            list(PAGES.keys()),
            label_visibility="collapsed",
        )

        st.divider()
        st.markdown("""
        <div style="font-size:0.72rem; color:#7fbf95; line-height:1.8; padding:4px 0;">
            📚 CSE494 – Intelligent NoSQL Databases<br>
            🎓 B.Tech Computer Science<br>
            🏫 Lovely Professional University
        </div>
        """, unsafe_allow_html=True)

    # ── DB connection check ───────────────────────────────────────────────────
    if not _check_db():
        st.stop()

    # ── Route to page module ──────────────────────────────────────────────────
    module_name = PAGES[selection]

    try:
        if module_name == "home":
            from ui_pages.home import render
        elif module_name == "manage_listings":
            from ui_pages.manage_listings import render
        elif module_name == "browse_food":
            from ui_pages.browse_food import render
        elif module_name == "smart_matching":
            from ui_pages.smart_matching import render
        elif module_name == "claims":
            from ui_pages.claims import render
        elif module_name == "analytics_dashboard":
            from ui_pages.analytics_dashboard import render
        elif module_name == "user_management":
            from ui_pages.user_management import render
        elif module_name == "query_explorer":
            from ui_pages.query_explorer import render
        else:
            st.error(f"Unknown page: {module_name}")
            return

        render()

    except Exception as exc:
        st.error(f"Page error: {exc}")
        logger.exception("Page render error for '%s'", module_name)
        if st.checkbox("Show debug traceback"):
            st.exception(exc)


if __name__ == "__main__":
    main()
