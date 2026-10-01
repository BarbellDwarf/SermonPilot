"""Front-door cutover metadata.

``GET /api/meta/retirement`` reports whether the operator has confirmed that
the console is serving their domain, computed from the ``web_console_ready``
key in the settings database (the same store the pipeline resolves). Default
False. Nothing in this repository flips it: the operator sets it and moves the
reverse-proxy upstream. Public: a single boolean, no secrets.

The response field is ``console_ready``. It carried the old interface's name
while that interface still existed, and the name outlived the thing it named.
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
    return {"console_ready": bool(_db_config().get("web_console_ready", False))}
