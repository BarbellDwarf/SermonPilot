"""
Signed authentication tokens.

The token is ``<expiry>.<hmac>`` and the HMAC is keyed by APP_PASSWORD, so it is
stateless, expires on schedule, and every existing token is revoked by changing
the password.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time


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
