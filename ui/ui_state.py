"""State-preserving Streamlit containers.

Streamlit recomputes an expander's ``expanded`` argument on every rerun and
resets unkeyed containers, so any interaction inside them (or anywhere else on
the page) snaps them back to their default open/closed state. Passing a stable
``key`` makes Streamlit persist the user's choice in Session State.

Pages should use :func:`managed_expander` / :func:`managed_popover` instead of
``st.expander`` / ``st.popover``. Keys are derived from the call site when not
given, so containers keep their state without per-call bookkeeping.
"""

from __future__ import annotations

import hashlib
import inspect
from typing import Any

import streamlit as _st


def _caller_key(prefix: str, label: str) -> str:
    frame = inspect.currentframe()
    while frame is not None and frame.f_globals.get("__name__") == __name__:
        frame = frame.f_back
    location = ""
    if frame is not None:
        location = f"{frame.f_code.co_filename}:{frame.f_lineno}"
    digest = hashlib.sha1(f"{location}|{label}".encode(), usedforsecurity=False).hexdigest()[:12]
    return f"ui_{prefix}_{digest}"


def keep_open(key: str, default: bool = False) -> bool:
    """Return the managed expanded state for a container key."""
    state_key = f"ui_open_{key}"
    if state_key not in _st.session_state:
        _st.session_state[state_key] = bool(default)
    return bool(_st.session_state[state_key])


def managed_expander(label: str, expanded: bool = False, *,
                     key: str | None = None, **kwargs: Any):
    """State-preserving ``st.expander``: the user's toggle survives reruns."""
    if key is None:
        key = _caller_key("expander", label)
    return _st.expander(label, expanded=expanded, key=key, **kwargs)


def managed_popover(label: str, *, key: str | None = None, **kwargs: Any):
    """State-preserving ``st.popover``: stays open across unrelated reruns."""
    if key is None:
        key = _caller_key("popover", label)
    return _st.popover(label, key=key, **kwargs)
