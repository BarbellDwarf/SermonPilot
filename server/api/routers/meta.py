"""Front-door cutover metadata (P6c).

GET /api/meta/retirement reports whether the Streamlit front door may be
retired, computed from the ``web_console_ready`` key in the settings database
(the same store the pipeline resolves). Default False; the operator flips the
key in Settings and moves the reverse-proxy upstream. Public: single boolean,
no secrets.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/meta", tags=["meta"])


def _db_config() -> dict:
    try:
        from ui.database import SermonDatabase

        stored = SermonDatabase().load_config()
    except Exception:
        return {}
    return stored if isinstance(stored, dict) else {}


@router.get("/retirement")
def retirement() -> dict:
    return {"streamlit_ready": bool(_db_config().get("web_console_ready", False))}
