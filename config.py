"""
config.py
---------
Central configuration module.

Reads environment variables from a .env file (via python-dotenv) and
exposes them as module-level constants that every other module imports.
Never import credentials anywhere else directly.
"""

import os
from dotenv import load_dotenv

# Load the .env file from the project root (same directory as this file).
load_dotenv()

# ── MongoDB ────────────────────────────────────────────────────────────────────
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "foodrescue")

# ── Application ────────────────────────────────────────────────────────────────
APP_SECRET: str = os.getenv("APP_SECRET", "dev_secret_change_me")
APP_ENV: str = os.getenv("APP_ENV", "development")

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
