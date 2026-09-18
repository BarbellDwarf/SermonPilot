"""Shared read-only mapping helpers (no database writes here)."""

from __future__ import annotations

import datetime
import json
from typing import Any


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "--:--"
    if total < 0:
        return "--:--"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _parse_ts(value: Any) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace(" ", "T", 1))
    except ValueError:
        return None


def job_duration(created: Any, completed: Any) -> str:
    start = _parse_ts(created)
    end = _parse_ts(completed)
    if start is None:
        return "waiting"
    if end is None:
        return "running"
    delta = max(0, int((end - start).total_seconds()))
    if delta < 60:
        return f"{delta}s"
    minutes, secs = divmod(delta, 60)
    if minutes < 60:
        return f"{minutes}m" if secs == 0 else f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def parse_json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def job_error(result: Any) -> str | None:
    data = parse_json(result, None)
    if not isinstance(data, dict):
        return None
    if data.get("success") is False or data.get("status") == "failed":
        for key in ("error", "message"):
            value = data.get(key)
            if value:
                return str(value)[:300]
        return "job failed"
    return None


def confidence_percent(value: Any) -> float:
    try:
        confidence = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if 0.0 <= confidence <= 1.0:
        return round(confidence * 100, 1)
    return round(confidence, 1)
