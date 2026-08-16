"""
Password authentication for the Streamlit UI.

When APP_PASSWORD is set, users must sign in before any page renders.
When it is unset, the app runs without authentication.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st

AUTH_SESSION_KEY = "authenticated"


def is_authenticated() -> bool:
    """Return True when no password is configured or the session is authenticated."""
    if not os.environ.get("APP_PASSWORD"):
        return True
    return bool(st.session_state.get(AUTH_SESSION_KEY, False))


def _password_matches(password: str) -> bool:
    expected = os.environ.get("APP_PASSWORD", "")
    return hmac.compare_digest(password, expected)


def render_login() -> None:
    """Render the login form and authenticate the session on success."""
    st.title("SermonPilot")
    st.subheader("Sign in to continue")
    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if _password_matches(password):
            st.session_state[AUTH_SESSION_KEY] = True
            st.rerun()
        else:
            st.error("Incorrect password")
