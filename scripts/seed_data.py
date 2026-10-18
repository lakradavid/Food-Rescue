"""
scripts/seed_data.py
--------------------
Inserts realistic fictional sample data into MongoDB.

Safe to re-run: uses upsert / duplicate-check logic so running the
script twice will NOT create duplicate users or listings.

Run from the foodrescue/ project root:
    python scripts/seed_data.py

Data inserted
─────────────
  • 5 donors  (restaurants, canteens, hostels)
  • 5 recipients / volunteers
  • 12 food listings (various categories, statuses, deadlines)
  •  8 claims  (pending, confirmed, completed, cancelled)
  •  6 rescue records (completed rescues, for analytics)
"""

from __future__ import annotations

import sys
import os

# Allow running from project root or scripts/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone, timedelta

import bcrypt
from bson import ObjectId

from database import init_db, get_db


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(hours_offset: float) -> datetime:
    """Return a UTC datetime offset by `hours_offset` from now."""
    return _now() + timedelta(hours=hours_offset)


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _upsert_user(db, doc: dict) -> ObjectId:
    """
    Insert user if email doesn't exist; return the _id either way.
    """
    existing = db.users.find_one({"email": doc["email"]})
    if existing:
        return existing["_id"]
    result = db.users.insert_one(doc)
    return result.inserted_id


# ─────────────────────────────────────────────────────────────────────────────
#  Users
# ─────────────────────────────────────────────────────────────────────────────

def seed_users(db) -> dict[str, ObjectId]:
    """Seed 5 donors and 5 recipients/volunteers. Returns {name_key: ObjectId}."""

    users_data = [
        # ── Donors ─────────────────────────────────────────────────────────
        {
            "name":          "Sunrise Café",
            "email":         "sunrise.cafe@example.com",
            "role":          "donor",
            "phone":         "+91 98100 11111",
            "location":      "LPU Campus, Block 32",
            "organization":  "Sunrise Café & Catering",
            "password_hash": _hash("cafe1234"),
            "active":        True,
            "created_at":    _dt(-30 * 24),
        },
        {
            "name":          "LPU Main Cafeteria",
            "email":         "lpu.cafeteria@example.com",
            "role":          "donor",
            "phone":         "+91 98100 22222",
            "location":      "LPU University Block",
            "organization":  "Lovely Professional University",
            "password_hash": _hash("cafe1234"),
            "active":        True,
            "created_at":    _dt(-25 * 24),
        },
        {
            "name":          "Green Bowl Restaurant",
            "email":         "greenbowl@example.com",
            "role":          "donor",
            "phone":         "+91 98100 33333",
            "location":      "Phagwara Market, GT Road",
            "organization":  "Green Bowl Pvt Ltd",
            "password_hash": _hash("cafe1234"),
            "active":        True,
            "created_at":    _dt(-20 * 24),
        },
        {
            "name":          "Girls Hostel Kitchen",
            "email":         "ghostel.kitchen@example.com",
            "role":          "donor",
            "phone":         "+91 98100 44444",
            "location":      "LPU Girls Hostel, Block H7",
            "organization":  "LPU Hostel Management",
            "password_hash": _hash("cafe1234"),
            "active":        True,
            "created_at":    _dt(-15 * 24),
        },
        {
            "name":          "Param Bakery",
            "email":         "param.bakery@example.com",
            "role":          "donor",
            "phone":         "+91 98100 55555",
            "location":      "Jalandhar Bypass, Near Bus Stand",
            "organization":  "Param Bakers & Confectioners",
            "password_hash": _hash("cafe1234"),
            "active":        True,
            "created_at":    _dt(-10 * 24),
        },
        # ── Recipients / Volunteers ─────────────────────────────────────────
        {
            "name":          "Ravi Kumar",
            "email":         "ravi.kumar@example.com",
            "role":          "recipient",
            "phone":         "+91 99900 10001",
            "location":      "LPU Campus, Block 34",
            "organization":  None,
            "password_hash": _hash("ravi1234"),
            "active":        True,
            "created_at":    _dt(-28 * 24),
        },
        {
            "name":          "Neha Singh",
            "email":         "neha.singh@example.com",
            "role":          "recipient",
            "phone":         "+91 99900 10002",
            "location":      "LPU Campus, Block 38",
            "organization":  None,
            "password_hash": _hash("neha1234"),
            "active":        True,
            "created_at":    _dt(-22 * 24),
        },
        {
            "name":          "Volunteer – Arjun Mehta",
            "email":         "arjun.mehta@example.com",
            "role":          "volunteer",
            "phone":         "+91 99900 10003",
            "location":      "Phagwara Market",
            "organization":  "NSS LPU Chapter",
            "password_hash": _hash("arjun1234"),
            "active":        True,
            "created_at":    _dt(-18 * 24),
        },
        {
            "name":          "Priya Sharma",
            "email":         "priya.sharma@example.com",
            "role":          "recipient",
            "phone":         "+91 99900 10004",
            "location":      "LPU Girls Hostel",
            "organization":  None,
            "password_hash": _hash("priya1234"),
            "active":        True,
            "created_at":    _dt(-12 * 24),
        },
        {
            "name":          "Volunteer – Deepak Rao",
            "email":         "deepak.rao@example.com",
            "role":          "volunteer",
            "phone":         "+91 99900 10005",
            "location":      "Jalandhar Bypass",
            "organization":  "Food Bank Punjab",
            "password_hash": _hash("deepak1234"),
            "active":        True,
            "created_at":    _dt(-8 * 24),
        },
    ]

    ids: dict[str, ObjectId] = {}
    keys = [
        "sunrise_cafe", "lpu_cafeteria", "green_bowl",
        "girls_hostel", "param_bakery",
        "ravi", "neha", "arjun", "priya", "deepak",
    ]
    for key, doc in zip(keys, users_data):
        ids[key] = _upsert_user(db, doc)

    print(f"  ✓ Users seeded ({len(ids)} records)")
    return ids


# ─────────────────────────────────────────────────────────────────────────────
#  Food Listings
# ─────────────────────────────────────────────────────────────────────────────

def seed_listings(db, user_ids: dict[str, ObjectId]) -> dict[str, ObjectId]:
    """Seed 12 food listings with varied categories, statuses, deadlines."""

    listings_data = [
        # 1 ── available, future deadline
        {
            "title":            "Dal Makhani + Jeera Rice",
            "category":         "Cooked Meal",
            "description":      "Freshly cooked dal makhani with steamed jeera rice. No added preservatives.",
            "quantity":         15.0,
            "claimed_quantity": 0.0,
            "unit":             "kg",
            "donor_id":         user_ids["lpu_cafeteria"],
            "pickup_location":  "LPU University Block",
            "status":           "available",
            "prepared_at":      _dt(-2),
            "pickup_deadline":  _dt(4),
            "allergens":        ["dairy", "gluten"],
            "created_at":       _dt(-2),
            "updated_at":       None,
        },
        # 2 ── available, ~6 hrs
        {
            "title":            "Assorted Bread Loaves",
            "category":         "Bakery & Bread",
            "description":      "Mixed white and brown bread, baked this morning. Best consumed by evening.",
            "quantity":         8.0,
            "claimed_quantity": 2.0,
            "unit":             "kg",
            "donor_id":         user_ids["param_bakery"],
            "pickup_location":  "Jalandhar Bypass, Near Bus Stand",
            "status":           "reserved",
            "prepared_at":      _dt(-6),
            "pickup_deadline":  _dt(6),
            "allergens":        ["gluten"],
            "created_at":       _dt(-6),
            "updated_at":       _dt(-1),
        },
        # 3 ── available
        {
            "title":            "Mixed Seasonal Vegetables",
            "category":         "Fruits & Vegetables",
            "description":      "Surplus tomatoes, capsicum, and onions from today's prep.",
            "quantity":         12.0,
            "claimed_quantity": 0.0,
            "unit":             "kg",
            "donor_id":         user_ids["green_bowl"],
            "pickup_location":  "Phagwara Market, GT Road",
            "status":           "available",
            "prepared_at":      _dt(-3),
            "pickup_deadline":  _dt(9),
            "allergens":        [],
            "created_at":       _dt(-3),
            "updated_at":       None,
        },
        # 4 ── available
        {
            "title":            "Paneer Butter Masala",
            "category":         "Cooked Meal",
            "description":      "Leftover from lunch service. Kept in food-safe containers at proper temperature.",
            "quantity":         6.0,
            "claimed_quantity": 0.0,
            "unit":             "kg",
            "donor_id":         user_ids["sunrise_cafe"],
            "pickup_location":  "LPU Campus, Block 32",
            "status":           "available",
            "prepared_at":      _dt(-3),
            "pickup_deadline":  _dt(3),
            "allergens":        ["dairy"],
            "created_at":       _dt(-3),
            "updated_at":       None,
        },
        # 5 ── available
        {
            "title":            "Packaged Fruit Juice Cartons",
            "category":         "Beverages",
            "description":      "120 cartons of 200ml mixed fruit juice, 2 days before best-before date.",
            "quantity":         24.0,
            "claimed_quantity": 0.0,
            "unit":             "litres",
            "donor_id":         user_ids["lpu_cafeteria"],
            "pickup_location":  "LPU University Block",
            "status":           "available",
            "prepared_at":      _dt(-5),
            "pickup_deadline":  _dt(48),
            "allergens":        [],
            "created_at":       _dt(-5),
            "updated_at":       None,
        },
        # 6 ── available
        {
            "title":            "Hostel Dinner Surplus – Rice & Rajma",
            "category":         "Cooked Meal",
            "description":      "Surplus dinner prepared for 200 students; approx 40 servings unclaimed.",
            "quantity":         40.0,
            "claimed_quantity": 10.0,
            "unit":             "servings",
            "donor_id":         user_ids["girls_hostel"],
            "pickup_location":  "LPU Girls Hostel, Block H7",
            "status":           "reserved",
            "prepared_at":      _dt(-1),
            "pickup_deadline":  _dt(2),
            "allergens":        ["gluten"],
            "created_at":       _dt(-1),
            "updated_at":       _dt(-0.5),
        },
        # 7 ── available
        {
            "title":            "Whole Wheat Biscuit Packets",
            "category":         "Snacks & Sweets",
            "description":      "50 packets of 200g whole wheat biscuits, 5 days to expiry.",
            "quantity":         10.0,
            "claimed_quantity": 0.0,
            "unit":             "kg",
            "donor_id":         user_ids["param_bakery"],
            "pickup_location":  "Jalandhar Bypass, Near Bus Stand",
            "status":           "available",
            "prepared_at":      _dt(-24),
            "pickup_deadline":  _dt(5 * 24),
            "allergens":        ["gluten"],
            "created_at":       _dt(-24),
            "updated_at":       None,
        },
        # 8 ── available
        {
            "title":            "Basmati Rice (surplus stock)",
            "category":         "Grains & Pulses",
            "description":      "25 kg surplus from monthly procurement. Sealed bags.",
            "quantity":         25.0,
            "claimed_quantity": 0.0,
            "unit":             "kg",
            "donor_id":         user_ids["lpu_cafeteria"],
            "pickup_location":  "LPU University Block",
            "status":           "available",
            "prepared_at":      _dt(-48),
            "pickup_deadline":  _dt(7 * 24),
            "allergens":        [],
            "created_at":       _dt(-48),
            "updated_at":       None,
        },
        # 9 ── rescued (fully claimed, for analytics)
        {
            "title":            "Chole Bhature – Morning Surplus",
            "category":         "Cooked Meal",
            "description":      "Morning breakfast surplus.",
            "quantity":         10.0,
            "claimed_quantity": 10.0,
            "unit":             "kg",
            "donor_id":         user_ids["sunrise_cafe"],
            "pickup_location":  "LPU Campus, Block 32",
            "status":           "rescued",
            "prepared_at":      _dt(-5 * 24),
            "pickup_deadline":  _dt(-4 * 24),
            "allergens":        ["gluten", "dairy"],
            "created_at":       _dt(-5 * 24),
            "updated_at":       _dt(-4 * 24),
        },
        # 10 ── rescued
        {
            "title":            "Banana Bunch (overripe)",
            "category":         "Fruits & Vegetables",
            "description":      "Ripe bananas from fruit stall – suitable for smoothies or baking.",
            "quantity":         20.0,
            "claimed_quantity": 20.0,
            "unit":             "kg",
            "donor_id":         user_ids["green_bowl"],
            "pickup_location":  "Phagwara Market, GT Road",
            "status":           "rescued",
            "prepared_at":      _dt(-8 * 24),
            "pickup_deadline":  _dt(-7 * 24),
            "allergens":        [],
            "created_at":       _dt(-8 * 24),
            "updated_at":       _dt(-7 * 24),
        },
        # 11 ── rescued
        {
            "title":            "Masala Chai – Bulk Flask",
            "category":         "Beverages",
            "description":      "6 large flasks of masala chai prepared for event, event cancelled.",
            "quantity":         18.0,
            "claimed_quantity": 18.0,
            "unit":             "litres",
            "donor_id":         user_ids["lpu_cafeteria"],
            "pickup_location":  "LPU University Block",
            "status":           "rescued",
            "prepared_at":      _dt(-3 * 24),
            "pickup_deadline":  _dt(-2.5 * 24),
            "allergens":        ["dairy"],
            "created_at":       _dt(-3 * 24),
            "updated_at":       _dt(-2.5 * 24),
        },
        # 12 ── expired
        {
            "title":            "Idli Sambhar Combo",
            "category":         "Cooked Meal",
            "description":      "South Indian breakfast surplus, missed pickup window.",
            "quantity":         8.0,
            "claimed_quantity": 0.0,
            "unit":             "kg",
            "donor_id":         user_ids["girls_hostel"],
            "pickup_location":  "LPU Girls Hostel, Block H7",
            "status":           "expired",
            "prepared_at":      _dt(-10 * 24),
            "pickup_deadline":  _dt(-9 * 24),
            "allergens":        ["gluten"],
            "created_at":       _dt(-10 * 24),
            "updated_at":       _dt(-9 * 24),
        },
    ]

    listing_ids: dict[str, ObjectId] = {}
    keys = [
        "dal_makhani", "bread", "vegetables", "paneer",
        "juice", "rice_rajma", "biscuits", "basmati",
        "chole_rescued", "banana_rescued", "chai_rescued", "idli_expired",
    ]

    for key, doc in zip(keys, listings_data):
        # Idempotent: check by title + donor_id
        existing = db.food_listings.find_one({
            "title":    doc["title"],
            "donor_id": doc["donor_id"],
        })
        if existing:
            listing_ids[key] = existing["_id"]
        else:
            result = db.food_listings.insert_one(doc)
            listing_ids[key] = result.inserted_id

    print(f"  ✓ Food listings seeded ({len(listing_ids)} records)")
    return listing_ids


# ─────────────────────────────────────────────────────────────────────────────
#  Claims
# ─────────────────────────────────────────────────────────────────────────────

def seed_claims(
    db,
    user_ids: dict[str, ObjectId],
    listing_ids: dict[str, ObjectId],
) -> dict[str, ObjectId]:
    """Seed 8 claims with varied statuses."""

    claims_data = [
        # Completed claims (match rescued listings)
        {
            "listing_id":       listing_ids["chole_rescued"],
            "claimant_id":      user_ids["ravi"],
            "claimed_quantity": 10.0,
            "status":           "completed",
            "created_at":       _dt(-4.5 * 24),
            "updated_at":       _dt(-4 * 24),
            "notes":            "Collected on time. Great food!",
        },
        {
            "listing_id":       listing_ids["banana_rescued"],
            "claimant_id":      user_ids["arjun"],
            "claimed_quantity": 20.0,
            "status":           "completed",
            "created_at":       _dt(-7.5 * 24),
            "updated_at":       _dt(-7 * 24),
            "notes":            "Distributed to shelter home.",
        },
        {
            "listing_id":       listing_ids["chai_rescued"],
            "claimant_id":      user_ids["neha"],
            "claimed_quantity": 18.0,
            "status":           "completed",
            "created_at":       _dt(-3 * 24),
            "updated_at":       _dt(-2.5 * 24),
            "notes":            "Served at study group session.",
        },
        # Confirmed claims (active listings)
        {
            "listing_id":       listing_ids["bread"],
            "claimant_id":      user_ids["deepak"],
            "claimed_quantity": 2.0,
            "status":           "confirmed",
            "created_at":       _dt(-1),
            "updated_at":       _dt(-0.5),
            "notes":            "Will pick up by 5 PM.",
        },
        {
            "listing_id":       listing_ids["rice_rajma"],
            "claimant_id":      user_ids["priya"],
            "claimed_quantity": 10.0,
            "status":           "confirmed",
            "created_at":       _dt(-0.5),
            "updated_at":       _dt(-0.25),
            "notes":            "For hostel common room.",
        },
        # Pending claims
        {
            "listing_id":       listing_ids["dal_makhani"],
            "claimant_id":      user_ids["ravi"],
            "claimed_quantity": 5.0,
            "status":           "pending",
            "created_at":       _dt(-0.5),
            "updated_at":       None,
            "notes":            None,
        },
        {
            "listing_id":       listing_ids["paneer"],
            "claimant_id":      user_ids["arjun"],
            "claimed_quantity": 3.0,
            "status":           "pending",
            "created_at":       _dt(-0.3),
            "updated_at":       None,
            "notes":            "Can collect within the hour.",
        },
        # Cancelled claim
        {
            "listing_id":       listing_ids["vegetables"],
            "claimant_id":      user_ids["neha"],
            "claimed_quantity": 5.0,
            "status":           "cancelled",
            "created_at":       _dt(-2 * 24),
            "updated_at":       _dt(-1.9 * 24),
            "notes":            "Could not make it, cancelled.",
        },
    ]

    claim_ids: dict[str, ObjectId] = {}
    keys = [
        "claim_chole", "claim_banana", "claim_chai",
        "claim_bread_confirmed", "claim_rice_confirmed",
        "claim_dal_pending", "claim_paneer_pending",
        "claim_veg_cancelled",
    ]

    for key, doc in zip(keys, claims_data):
        existing = db.claims.find_one({
            "listing_id":  doc["listing_id"],
            "claimant_id": doc["claimant_id"],
        })
        if existing:
            claim_ids[key] = existing["_id"]
        else:
            result = db.claims.insert_one(doc)
            claim_ids[key] = result.inserted_id

    print(f"  ✓ Claims seeded ({len(claim_ids)} records)")
    return claim_ids


# ─────────────────────────────────────────────────────────────────────────────
#  Rescue Records
# ─────────────────────────────────────────────────────────────────────────────

def seed_rescue_records(
    db,
    user_ids:    dict[str, ObjectId],
    listing_ids: dict[str, ObjectId],
    claim_ids:   dict[str, ObjectId],
) -> None:
    """Seed 6 rescue records matching the 3 completed + 3 earlier rescues."""

    records = [
        # Matching completed claims above
        {
            "claim_id":         claim_ids["claim_chole"],
            "listing_id":       listing_ids["chole_rescued"],
            "donor_id":         user_ids["sunrise_cafe"],
            "recipient_id":     user_ids["ravi"],
            "rescued_quantity": 10.0,
            "unit":             "kg",
            "category":         "Cooked Meal",
            "food_title":       "Chole Bhature – Morning Surplus",
            "pickup_location":  "LPU Campus, Block 32",
            "rescued_at":       _dt(-4 * 24),
        },
        {
            "claim_id":         claim_ids["claim_banana"],
            "listing_id":       listing_ids["banana_rescued"],
            "donor_id":         user_ids["green_bowl"],
            "recipient_id":     user_ids["arjun"],
            "rescued_quantity": 20.0,
            "unit":             "kg",
            "category":         "Fruits & Vegetables",
            "food_title":       "Banana Bunch (overripe)",
            "pickup_location":  "Phagwara Market, GT Road",
            "rescued_at":       _dt(-7 * 24),
        },
        {
            "claim_id":         claim_ids["claim_chai"],
            "listing_id":       listing_ids["chai_rescued"],
            "donor_id":         user_ids["lpu_cafeteria"],
            "recipient_id":     user_ids["neha"],
            "rescued_quantity": 18.0,
            "unit":             "litres",
            "category":         "Beverages",
            "food_title":       "Masala Chai – Bulk Flask",
            "pickup_location":  "LPU University Block",
            "rescued_at":       _dt(-2.5 * 24),
        },
        # Additional historical rescues (for richer analytics/trends)
        {
            "claim_id":         ObjectId(),   # synthetic past claim
            "listing_id":       ObjectId(),
            "donor_id":         user_ids["lpu_cafeteria"],
            "recipient_id":     user_ids["deepak"],
            "rescued_quantity": 14.0,
            "unit":             "kg",
            "category":         "Cooked Meal",
            "food_title":       "Lunch Surplus – Aloo Gobi",
            "pickup_location":  "LPU University Block",
            "rescued_at":       _dt(-15 * 24),
        },
        {
            "claim_id":         ObjectId(),
            "listing_id":       ObjectId(),
            "donor_id":         user_ids["param_bakery"],
            "recipient_id":     user_ids["priya"],
            "rescued_quantity": 6.0,
            "unit":             "kg",
            "category":         "Bakery & Bread",
            "food_title":       "Evening Bread Surplus",
            "pickup_location":  "Jalandhar Bypass, Near Bus Stand",
            "rescued_at":       _dt(-20 * 24),
        },
        {
            "claim_id":         ObjectId(),
            "listing_id":       ObjectId(),
            "donor_id":         user_ids["girls_hostel"],
            "recipient_id":     user_ids["arjun"],
            "rescued_quantity": 25.0,
            "unit":             "servings",
            "category":         "Cooked Meal",
            "food_title":       "Weekend Dinner Surplus",
            "pickup_location":  "LPU Girls Hostel, Block H7",
            "rescued_at":       _dt(-10 * 24),
        },
    ]

    count = 0
    for doc in records:
        existing = db.rescue_records.find_one({"claim_id": doc["claim_id"]})
        if not existing:
            db.rescue_records.insert_one(doc)
            count += 1

    print(f"  ✓ Rescue records seeded ({count} new records)")


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_seed() -> None:
    print("\n🌱  FoodRescue – Seed Script")
    print("=" * 40)

    try:
        db = init_db()
        print("  ✓ Connected to MongoDB")
    except Exception as exc:
        print(f"  ✗ Cannot connect to MongoDB: {exc}")
        print("    Make sure MongoDB is running and MONGO_URI is set in .env")
        sys.exit(1)

    print("\nInserting sample data...")
    user_ids    = seed_users(db)
    listing_ids = seed_listings(db, user_ids)
    claim_ids   = seed_claims(db, user_ids, listing_ids)
    seed_rescue_records(db, user_ids, listing_ids, claim_ids)

    print("\n✅  Seed complete.  Summary:")
    print(f"   Users:          {db.users.count_documents({})}")
    print(f"   Food listings:  {db.food_listings.count_documents({})}")
    print(f"   Claims:         {db.claims.count_documents({})}")
    print(f"   Rescue records: {db.rescue_records.count_documents({})}")
    print()
    print("Demo credentials (all passwords: cafe1234 / ravi1234 etc.)")
    print("  Donor:     sunrise.cafe@example.com      / cafe1234")
    print("  Recipient: ravi.kumar@example.com        / ravi1234")
    print("  Volunteer: arjun.mehta@example.com       / arjun1234")


if __name__ == "__main__":
    run_seed()
