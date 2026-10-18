"""
pages/user_management.py
------------------------
User registration and management page.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import timezone

from database import get_db
from services.user_service import (
    register_user,
    fetch_users,
    edit_user,
    deactivate_user,
    user_role_counts,
)
from config import USER_ROLES


def _fmt_dt(dt):
    if dt is None:
        return "—"
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d %b %Y")


def render():
    st.title("👥 User Management")
    st.caption("Register donors, recipients, and volunteers.")

    db = get_db()

    # ── Role summary ──────────────────────────────────────────────────────────
    counts = user_role_counts(db)
    total  = sum(counts.values())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👥 Total Users",   total)
    c2.metric("🍱 Donors",        counts.get("donor",     0))
    c3.metric("🙋 Recipients",    counts.get("recipient", 0))
    c4.metric("🤝 Volunteers",    counts.get("volunteer", 0))

    st.divider()

    tab_list, tab_register, tab_edit, tab_deactivate = st.tabs([
        "📋 All Users", "➕ Register", "✏️ Edit", "🚫 Deactivate"
    ])

    # ── TAB: All users ────────────────────────────────────────────────────────
    with tab_list:
        st.subheader("Registered Users")

        role_filter = st.selectbox("Filter by role:", ["All"] + USER_ROLES, key="list_role")
        role_arg    = None if role_filter == "All" else role_filter
        users       = fetch_users(db, role=role_arg)

        if not users:
            st.info("No users found.")
        else:
            rows = [
                {
                    "Name":         u.get("name", "—"),
                    "Email":        u.get("email", "—"),
                    "Role":         u.get("role", "—").capitalize(),
                    "Phone":        u.get("phone") or "—",
                    "Location":     u.get("location") or "—",
                    "Organization": u.get("organization") or "—",
                    "Registered":   _fmt_dt(u.get("created_at")),
                    "Active":       "✅" if u.get("active", True) else "❌",
                }
                for u in users
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # ── TAB: Register ─────────────────────────────────────────────────────────
    with tab_register:
        st.subheader("Register a New User")
        st.caption("Passwords are hashed with bcrypt before storage. Never stored in plain text.")

        with st.form("register_form", clear_on_submit=True):
            name     = st.text_input("Full Name *", placeholder="e.g. Ravi Kumar")
            email    = st.text_input("Email Address *", placeholder="ravi@example.com")
            role     = st.selectbox("Role *", USER_ROLES,
                                    format_func=lambda r: r.capitalize())
            password = st.text_input("Password (min 6 chars)", type="password")
            phone    = st.text_input("Phone", placeholder="+91 98765 43210")
            location = st.text_input("Location", placeholder="e.g. LPU Campus, Block 34")
            org      = st.text_input("Organization (optional)", placeholder="e.g. NSS LPU")

            submitted = st.form_submit_button("✅ Register", type="primary")

        if submitted:
            form_data = {
                "name": name, "email": email, "role": role,
                "password": password, "phone": phone,
                "location": location, "organization": org,
            }
            ok, result = register_user(db, form_data)
            if ok:
                st.success(f"✅ User registered! ID: {result}")
                st.rerun()
            else:
                st.error(f"Registration failed:\n{result}")

    # ── TAB: Edit ─────────────────────────────────────────────────────────────
    with tab_edit:
        st.subheader("Edit User Details")
        st.caption("Email and role cannot be changed here to preserve data integrity.")

        users = fetch_users(db)
        if not users:
            st.info("No users to edit.")
        else:
            user_map = {f"{u['name']} — {u['email']} ({u['role']})": u for u in users}
            sel_label = st.selectbox("Select user:", list(user_map.keys()), key="edit_user_sel")
            sel_user  = user_map[sel_label]

            with st.form("edit_user_form"):
                new_name  = st.text_input("Name",         value=sel_user.get("name", ""))
                new_phone = st.text_input("Phone",        value=sel_user.get("phone") or "")
                new_loc   = st.text_input("Location",     value=sel_user.get("location") or "")
                new_org   = st.text_input("Organization", value=sel_user.get("organization") or "")

                save = st.form_submit_button("💾 Save Changes", type="primary")

            if save:
                updates = {
                    "name": new_name, "phone": new_phone,
                    "location": new_loc, "organization": new_org,
                }
                ok, msg = edit_user(db, str(sel_user["_id"]), updates)
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"Update failed: {msg}")

    # ── TAB: Deactivate ───────────────────────────────────────────────────────
    with tab_deactivate:
        st.subheader("Deactivate a User")
        st.caption(
            "Deactivation is a soft delete — the user document is retained "
            "to preserve referential integrity in existing listings and claims."
        )

        users = fetch_users(db)
        active_users = [u for u in users if u.get("active", True)]

        if not active_users:
            st.info("No active users to deactivate.")
        else:
            da_map   = {f"{u['name']} — {u['email']} ({u['role']})": u for u in active_users}
            da_label = st.selectbox("Select user:", list(da_map.keys()), key="da_sel")
            da_user  = da_map[da_label]

            st.warning(
                f"Deactivating **{da_user['name']}** will prevent them from "
                "logging in but will keep their historical data intact."
            )
            confirm = st.checkbox("I confirm I want to deactivate this user.")
            if st.button("🚫 Deactivate", type="primary", disabled=not confirm):
                ok, msg = deactivate_user(db, str(da_user["_id"]))
                if ok:
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"Failed: {msg}")
