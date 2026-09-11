"""
Password authentication for the Streamlit UI.

When APP_PASSWORD is set, users must sign in before any page renders.
When it is unset, the app runs without authentication.

Sessions survive browser refreshes through a signed cookie: the token is
``<expiry>.<hmac>`` and the HMAC is keyed by APP_PASSWORD, so it is stateless,
expires on schedule, and every existing session is revoked by changing the
password. The cookie is not HttpOnly (it is set by JavaScript) and not Secure
(LAN deployments are plain HTTP); it carries no secret, only a signature.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

import streamlit as st

AUTH_SESSION_KEY = "authenticated"
AUTH_COOKIE_NAME = "sermonpilot_auth"
AUTH_SESSION_DAYS = 30


def is_authenticated() -> bool:
    """Return True when no password is configured or the session/cookie is authenticated."""
    if not os.environ.get("APP_PASSWORD"):
        return True
    if st.session_state.get(AUTH_SESSION_KEY, False):
        return True
    token = _cookie_token()
    if token and valid_token(token):
        st.session_state[AUTH_SESSION_KEY] = True
        return True
    return False


def sign_out() -> None:
    """Clear the authenticated session and its persistent cookie."""
    st.session_state[AUTH_SESSION_KEY] = False
    _write_cookie("", max_age=0)


def _password_matches(password: str) -> bool:
    expected = os.environ.get("APP_PASSWORD", "")
    return hmac.compare_digest(password, expected)


def _sign(expiry: str) -> str:
    key = os.environ.get("APP_PASSWORD", "").encode()
    return hmac.new(key, f"sermonpilot-auth:{expiry}".encode(), hashlib.sha256).hexdigest()


def make_token(expiry: int) -> str:
    """Build a signed token that expires at the given epoch second."""
    expiry_str = str(int(expiry))
    return f"{expiry_str}.{_sign(expiry_str)}"


def valid_token(token: str) -> bool:
    """Return True when the token signature matches and it has not expired."""
    try:
        expiry_str, signature = token.split(".", 1)
        expiry = int(expiry_str)
    except (AttributeError, ValueError):
        return False
    if expiry < time.time():
        return False
    return hmac.compare_digest(signature, _sign(expiry_str))


def _cookie_token() -> str | None:
    try:
        return st.context.cookies.get(AUTH_COOKIE_NAME)
    except Exception:
        return None


def _write_cookie(value: str, max_age: int = AUTH_SESSION_DAYS * 86400) -> None:
    from streamlit.components.v1 import html as components_html

    script = (
        "<script>"
        f"document.cookie='{AUTH_COOKIE_NAME}={value}; path=/; "
        f"max-age={max_age}; SameSite=Lax';"
        "</script>"
    )
    components_html(script, height=0)


def _set_auth_cookie() -> None:
    expiry = int(time.time()) + AUTH_SESSION_DAYS * 86400
    _write_cookie(make_token(expiry))


def render_login() -> None:
    """Render the login form and authenticate the session on success."""
    from ui.version import app_version

    st.title("SermonPilot")
    st.subheader("Sign in to continue")
    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if _password_matches(password):
            st.session_state[AUTH_SESSION_KEY] = True
            _set_auth_cookie()
            st.rerun()
        else:
            st.error("Incorrect password")
    st.caption(f"v{app_version()}")
