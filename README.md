# 🥗 FoodRescue — Smart Food Waste Rescue & Analytics System

**Course:** CSE494 – Intelligent NoSQL Databases  
**University:** Lovely Professional University  
**Tech Stack:** Python · MongoDB · PyMongo · Streamlit · Plotly

---

## What This Project Does

FoodRescue lets restaurants, canteens, and hostels list surplus food so that
recipients and volunteers can claim and collect it before it expires.
The system demonstrates document-oriented database design, MongoDB validation,
PyMongo CRUD, six aggregation pipelines, and a Streamlit UI — all as required
by the CSE494 course project brief.

---

## Project Structure

```
foodrescue/
├── app.py                      ← Streamlit entry point
├── config.py                   ← Environment config + domain constants
├── database.py                 ← MongoDB connection, schema validators, indexes
├── validators.py               ← Application-level validation (runs before DB writes)
│
├── repositories/               ← Direct MongoDB operations (one file per collection)
│   ├── user_repo.py
│   ├── listing_repo.py
│   ├── claim_repo.py
│   └── rescue_repo.py
│
├── services/                   ← Business logic (coordinates repos + validators)
│   ├── user_service.py
│   ├── listing_service.py
│   ├── claim_service.py
│   └── matching_service.py
│
├── analytics/
│   └── pipelines.py            ← All 6 MongoDB aggregation pipelines
│
├── pages/                      ← One Streamlit page per module
│   ├── home.py
│   ├── manage_listings.py
│   ├── browse_food.py
│   ├── smart_matching.py
│   ├── claims.py
│   ├── analytics_dashboard.py
│   └── user_management.py
│
├── scripts/
│   └── seed_data.py            ← Sample data insertion script
│
├── tests/                      ← Pytest test suite
│   ├── conftest.py
│   ├── test_validators.py
│   ├── test_users.py
│   ├── test_listings.py
│   ├── test_claims.py
│   ├── test_analytics.py
│   └── test_matching.py
│
├── .env.example                ← Environment variable template
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10 or newer
- MongoDB Community Server (local) **or** a free MongoDB Atlas cluster
- Git

### 2. Clone and install

```bash
git clone <your-repo-url>
cd foodrescue
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set your connection string:

```
# Local MongoDB
MONGO_URI=mongodb://localhost:27017

# OR MongoDB Atlas
MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority

MONGO_DB_NAME=foodrescue
APP_SECRET=change_this_to_a_random_string
```

> **Never commit your real `.env` file.** It is in `.gitignore`.

### 4. Seed sample data

```bash
python scripts/seed_data.py
```

This inserts 5 donors, 5 recipients/volunteers, 12 food listings, 8 claims,
and 6 rescue records. Safe to run multiple times — uses upsert logic.

Demo credentials:
| Role      | Email                          | Password   |
|-----------|-------------------------------|------------|
| Donor     | sunrise.cafe@example.com      | cafe1234   |
| Recipient | ravi.kumar@example.com        | ravi1234   |
| Volunteer | arjun.mehta@example.com       | arjun1234  |

### 5. Run the application

```bash
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

### 6. Run tests

```bash
pytest tests/ -v
```

Tests use a separate `foodrescue_test` database and clean up after themselves.

---

## MongoDB Collections

### `users`
Stores donors, recipients, and volunteers.

```json
{
  "_id":           ObjectId,
  "name":          "Sunrise Café",
  "email":         "sunrise.cafe@example.com",
  "role":          "donor",
  "phone":         "+91 98100 11111",
  "location":      "LPU Campus, Block 32",
  "organization":  "Sunrise Café & Catering",
  "password_hash": "$2b$12$...",
  "active":        true,
  "created_at":    ISODate
}
```

### `food_listings`
Each surplus food item posted by a donor.

```json
{
  "_id":              ObjectId,
  "title":            "Dal Makhani + Jeera Rice",
  "category":         "Cooked Meal",
  "description":      "Freshly cooked...",
  "quantity":         15.0,
  "claimed_quantity": 0.0,
  "unit":             "kg",
  "donor_id":         ObjectId,
  "pickup_location":  "LPU University Block",
  "status":           "available",
  "prepared_at":      ISODate,
  "pickup_deadline":  ISODate,
  "allergens":        ["dairy", "gluten"],
  "created_at":       ISODate,
  "updated_at":       ISODate
}
```

### `claims`
One document per claim by a recipient or volunteer.

```json
{
  "_id":              ObjectId,
  "listing_id":       ObjectId,
  "claimant_id":      ObjectId,
  "claimed_quantity": 4.0,
  "status":           "pending",
  "created_at":       ISODate,
  "updated_at":       ISODate,
  "notes":            "Will collect at 3 PM"
}
```

### `rescue_records`
Immutable audit trail — created when a claim reaches `completed`.

```json
{
  "_id":              ObjectId,
  "claim_id":         ObjectId,
  "listing_id":       ObjectId,
  "donor_id":         ObjectId,
  "recipient_id":     ObjectId,
  "rescued_quantity": 4.0,
  "unit":             "kg",
  "category":         "Cooked Meal",
  "food_title":       "Dal Makhani + Jeera Rice",
  "pickup_location":  "LPU University Block",
  "rescued_at":       ISODate
}
```

**Embedding vs Referencing:**  
User details are *referenced* (ObjectId) rather than embedded in listings and
claims. This means a single authoritative user document; changes (e.g. phone
number) propagate automatically on lookup. The trade-off is an extra `$lookup`
when we need donor names alongside listings. For this scale, referencing is
the right choice. Rescue records *denormalise* category, location, and unit to
create an immutable historical record that remains accurate even if the
original listing or claim is deleted.

---

## Aggregation Pipelines

All six pipelines are in `analytics/pipelines.py` and documented inline.

| # | Pipeline | Collection | Key Stages |
|---|---|---|---|
| 1 | Total Food Rescued | `rescue_records` | `$group`, `$sort`, `$project` |
| 2 | Category Analysis | `food_listings` | `$group`, `$addFields`, `$sort`, `$project` |
| 3 | Rescue Success Rate | `claims` | `$group` + `$cond`, `$addFields`, `$project` |
| 4 | Location Analysis | both (merged) | two `$group` pipelines + Python merge |
| 5 | Donor Performance | `rescue_records` | `$group`, `$sort`, `$lookup`, `$unwind`, `$project` |
| 6 | Rescue Trends | `rescue_records` | `$group` + `$dateToString`, `$sort`, `$project` |

---

## Smart Matching Algorithm

Rule-based scoring (0–100 points). No ML, no external APIs.

| Signal | Points |
|---|---|
| Category matches preference | +40 |
| Location keyword matches | +30 |
| Deadline < 2 hours | +30 |
| Deadline 2–6 hours | +20 |
| Deadline 6–12 hours | +10 |
| Deadline > 12 hours | +5 |

Ties broken by earliest deadline. Every recommendation includes a
plain-English explanation string.

---

## Food Safety Notice

> FoodRescue does **not** certify any food as safe for consumption.
> Pickup deadlines and allergen information are provided by donors and are
> not independently verified. Food providers are solely responsible for
> ensuring food safety, correct storage temperatures, allergen labelling,
> and compliance with applicable local food handling regulations.

---

## Test Coverage

| File | What is tested |
|---|---|
| `test_validators.py` | All validation rules, no DB needed |
| `test_users.py` | Registration, duplicate email, auth, bcrypt |
| `test_listings.py` | CRUD, expiry sweep, owner check, category filter |
| `test_claims.py` | Full lifecycle, over-claim, double-claim, qty release |
| `test_analytics.py` | All 6 pipelines with controlled datasets |
| `test_matching.py` | Scoring, urgency, location, top-N, zero-qty exclusion |

---

## Architecture Notes

```
Streamlit pages
     ↓
  Services  (validation + business rules)
     ↓
  Repositories  (PyMongo queries)
     ↓
  MongoDB  (JSON Schema validators + indexes)
```

This layered design keeps MongoDB queries out of the UI code, makes the
business logic testable without Streamlit, and makes each layer replaceable
independently.
