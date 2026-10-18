"""
tests/test_users.py
-------------------
Integration tests for user registration and retrieval.
Requires a running MongoDB instance (uses the test DB via conftest).
"""

from __future__ import annotations

import pytest
from conftest import make_donor, make_recipient


class TestUserRegistration:

    def test_register_donor_succeeds(self, db):
        from services.user_service import register_user
        ok, uid = register_user(db, {
            "name": "Sunrise Café", "email": "sunrise@test.com",
            "role": "donor", "password": "secure123",
        })
        assert ok is True
        assert len(uid) == 24  # ObjectId hex string

    def test_register_recipient_succeeds(self, db):
        from services.user_service import register_user
        ok, uid = register_user(db, {
            "name": "Neha Singh", "email": "neha@test.com",
            "role": "recipient", "password": "secure123",
        })
        assert ok is True

    def test_register_volunteer_succeeds(self, db):
        from services.user_service import register_user
        ok, uid = register_user(db, {
            "name": "Arjun Mehta", "email": "arjun@test.com",
            "role": "volunteer", "password": "pass1234",
        })
        assert ok is True

    def test_duplicate_email_rejected(self, db):
        """Registering the same email twice must fail with a clear message."""
        from services.user_service import register_user
        data = {"name": "User One", "email": "dup@test.com",
                "role": "donor", "password": "pass1234"}
        ok1, _ = register_user(db, data)
        assert ok1 is True

        ok2, msg = register_user(db, {**data, "name": "User Two"})
        assert ok2 is False
        assert "already exists" in msg.lower()

    def test_short_password_rejected(self, db):
        from services.user_service import register_user
        ok, msg = register_user(db, {
            "name": "Test", "email": "pw@test.com",
            "role": "donor", "password": "abc",
        })
        assert ok is False
        assert "password" in msg.lower()

    def test_invalid_email_rejected(self, db):
        from services.user_service import register_user
        ok, msg = register_user(db, {
            "name": "Test", "email": "not-an-email",
            "role": "donor",
        })
        assert ok is False

    def test_missing_name_rejected(self, db):
        from services.user_service import register_user
        ok, msg = register_user(db, {
            "email": "noname@test.com", "role": "donor",
        })
        assert ok is False

    def test_password_not_stored_in_plain_text(self, db):
        """The raw password must never appear in the stored document."""
        from services.user_service import register_user
        raw_pw = "myplainpassword"
        register_user(db, {
            "name": "SafeUser", "email": "safe@test.com",
            "role": "donor", "password": raw_pw,
        })
        stored = db.users.find_one({"email": "safe@test.com"})
        assert stored is not None
        assert stored.get("password_hash") != raw_pw
        assert raw_pw not in str(stored)


class TestUserFetch:

    def test_fetch_by_id(self, db):
        from services.user_service import fetch_user
        uid = make_donor(db)
        user = fetch_user(db, uid)
        assert user is not None
        assert str(user["_id"]) == uid

    def test_fetch_by_email(self, db):
        from repositories.user_repo import get_user_by_email
        make_donor(db, email="lookup@test.com")
        user = get_user_by_email(db, "lookup@test.com")
        assert user is not None
        assert user["email"] == "lookup@test.com"

    def test_fetch_nonexistent_user_returns_none(self, db):
        from services.user_service import fetch_user
        result = fetch_user(db, "000000000000000000000000")
        assert result is None

    def test_fetch_donors_only(self, db):
        from services.user_service import fetch_donors, fetch_users
        make_donor(db,     email="d1@test.com")
        make_donor(db,     name="Donor 2", email="d2@test.com")
        make_recipient(db, email="r1@test.com")

        donors = fetch_donors(db)
        assert len(donors) == 2
        assert all(d["role"] == "donor" for d in donors)

    def test_role_counts(self, db):
        from services.user_service import user_role_counts
        make_donor(db,     email="d1@test.com")
        make_donor(db,     name="D2", email="d2@test.com")
        make_recipient(db, email="r1@test.com")

        counts = user_role_counts(db)
        assert counts.get("donor",     0) == 2
        assert counts.get("recipient", 0) == 1


class TestAuthentication:

    def test_correct_credentials_succeed(self, db):
        from services.user_service import register_user, authenticate_user
        register_user(db, {
            "name": "Auth User", "email": "auth@test.com",
            "role": "donor", "password": "correctpass",
        })
        ok, user = authenticate_user(db, "auth@test.com", "correctpass")
        assert ok is True
        assert isinstance(user, dict)
        assert user["email"] == "auth@test.com"

    def test_wrong_password_fails(self, db):
        from services.user_service import register_user, authenticate_user
        register_user(db, {
            "name": "Auth User2", "email": "auth2@test.com",
            "role": "donor", "password": "correctpass",
        })
        ok, msg = authenticate_user(db, "auth2@test.com", "wrongpass")
        assert ok is False
        assert "incorrect" in msg.lower()

    def test_unknown_email_fails(self, db):
        from services.user_service import authenticate_user
        ok, msg = authenticate_user(db, "nobody@test.com", "somepass")
        assert ok is False
        assert "no account" in msg.lower()
