"""
config.py
---------
Central configuration module.

Reads credentials from:
  1. Streamlit secrets (st.secrets) — used when deployed on Streamlit Community Cloud.
  2. .env file (via python-dotenv) — used for local development.
Never import credentials anywhere else directly.
"""

import os
from dotenv import load_dotenv

# Load .env for local development (no-op if file doesn't exist)
load_dotenv()

def _get(key: str, default: str = "") -> str:
    """Read from Streamlit secrets first, then env vars, then default."""
    try:
        import streamlit as st
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)

# ── MongoDB ────────────────────────────────────────────────────────────────────
MONGO_URI: str = _get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME: str = _get("MONGO_DB_NAME", "foodrescue")

# ── Application ────────────────────────────────────────────────────────────────
APP_SECRET: str = _get("APP_SECRET", "dev_secret_change_me")
APP_ENV: str = _get("APP_ENV", "development")

# ── Domain constants ──────────────────────────────────────────────────────────
# Allowed values for the food_listings.category field
FOOD_CATEGORIES: list[str] = [
    "Cooked Meal",
    "Bakery & Bread",
    "Fruits & Vegetables",
    "Dairy & Eggs",
    "Beverages",
    "Packaged Food",
    "Snacks & Sweets",
    "Grains & Pulses",
    "Other",
]

# Allowed units for quantity
QUANTITY_UNITS: list[str] = ["kg", "g", "litres", "ml", "servings", "pieces", "packets", "boxes"]

# Allowed status values for food_listings
LISTING_STATUSES: list[str] = ["available", "reserved", "rescued", "expired"]

# Allowed status values for claims
CLAIM_STATUSES: list[str] = ["pending", "confirmed", "completed", "cancelled"]

# Allowed roles for users
USER_ROLES: list[str] = ["donor", "recipient", "volunteer"]

# Conversion assumption: 1 kg of food ≈ this many meals (used for estimates only)
KG_TO_MEALS_ESTIMATE: float = 2.5
