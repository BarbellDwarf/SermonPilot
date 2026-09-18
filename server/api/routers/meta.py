"""Front-door cutover metadata (P6c).

GET /api/meta/retirement reports whether the Streamlit front door may be
retired, computed from the ``web_console_ready`` key in the live YAML config
(``SA_UPDATER_CONFIG`` or ``config.yaml``). Default False; the operator flips the key
and the operator moves the nginx upstream. Public: single boolean, no secrets.
"""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(prefix="/api/meta", tags=["meta"])


def _live_config() -> dict:
    path = os.environ.get("SA_UPDATER_CONFIG", "config.yaml")
    try:
        import yaml  # type: ignore[import-untyped]

        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@router.get("/retirement")
def retirement() -> dict:
    return {"streamlit_ready": bool(_live_config().get("web_console_ready", False))}
