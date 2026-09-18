"""Per-user data scoping: NULL = unowned/legacy = admin-visible only."""

from __future__ import annotations

import sqlite3
from typing import Any


def is_admin(user: dict[str, Any] | None) -> bool:
    return bool(user) and user.get("role") == "admin"


def request_user(request: Any) -> dict[str, Any] | None:
    return getattr(getattr(request, "state", None), "user", None)


def ownership_map(table: str) -> dict[str, str | None]:
    from server.api.db import ReadOnlySermonDatabase

    try:
        with ReadOnlySermonDatabase().get_connection() as conn:
            rows = conn.execute(f"SELECT id, user_id FROM {table}").fetchall()
    except sqlite3.OperationalError:
        return {}
    return {str(row["id"]): row["user_id"] for row in rows}


def scope_rows(
    rows: list[dict[str, Any]], user: dict[str, Any] | None, table: str
) -> list[dict[str, Any]]:
    if user is None:
        return []
    if is_admin(user):
        return rows
    owners = ownership_map(table)
    uid = user.get("id")
    out = []
    for row in rows:
        owner = row.get("user_id", owners.get(str(row.get("id"))))
        if owner == uid:
            out.append(row)
    return out


def visible(owner: str | None, user: dict[str, Any] | None) -> bool:
    if user is None:
        return False
    if is_admin(user):
        return True
    return owner == user.get("id")
