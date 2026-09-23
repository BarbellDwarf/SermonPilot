"""Resolve which SermonAudio connection a user's uploads will use.

Per-user connections live in ``user_settings`` under
``connections.sermonaudio``, the same store the console writes through
``/api/me/connections``. An upload uses the account the user picked as their
default (or the first account they own when no default is set).

The single-account fallback in the resolved app config (seeded from
``SERMONAUDIO_API_KEY`` / ``SERMONAUDIO_BROADCASTER_ID``) applies only while no
user has stored a connection anywhere. That keeps a fresh deployment usable
without letting one user publish with another user's credentials.

This module reads the settings database directly so the job executors and the
API can share one resolution path without importing each other.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SETTING_KEY = "connections.sermonaudio"
DEFAULT_DB_PATH = "/data/sermon_processor.db"

SOURCE_USER = "user"
SOURCE_NONE = "none"

CONNECT_ACCOUNT_MESSAGE = (
    "Connect your SermonAudio account in Settings before publishing."
)


@dataclass(frozen=True)
class SermonAudioConnection:
    """The credentials an upload would use, plus where they came from."""

    api_key: str = ""
    broadcaster_id: str = ""
    source: str = SOURCE_NONE
    account_id: str | None = None
    account_name: str | None = None

    @property
    def usable(self) -> bool:
        return bool(self.api_key and self.broadcaster_id)

    def masked_key(self) -> str:
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "*" * 8
        return "*" * 8 + self.api_key[-4:]


def db_path() -> str:
    """Settings database path, matching the server and job-queue resolution."""
    return (
        os.environ.get("SERMONPILOT_DB")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_DB_PATH
    )


def _deobfuscate(stored: object) -> str:
    if not isinstance(stored, str) or not stored:
        return ""
    try:
        return base64.b64decode(stored.encode()).decode()
    except Exception:
        return ""


def _open(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _blob_for_user(conn: sqlite3.Connection, user_id: str) -> dict:
    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND key = ?",
        (user_id, SETTING_KEY),
    ).fetchone()
    if row is None:
        return {}
    try:
        value = json.loads(row["value"])
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _item_connection(item: dict, source: str) -> SermonAudioConnection:
    return SermonAudioConnection(
        api_key=_deobfuscate(item.get("_apiKeyEnc")),
        broadcaster_id=str(item.get("broadcasterId") or "").strip(),
        source=source,
        account_id=str(item.get("id") or "") or None,
        account_name=str(item.get("name") or "") or None,
    )


def _usable_item(blob: dict) -> dict | None:
    items = blob.get("items")
    if not isinstance(items, list):
        return None
    default_id = blob.get("default_id")
    candidates = [i for i in items if isinstance(i, dict)]
    if default_id is not None:
        for item in candidates:
            if item.get("id") == default_id and _item_connection(item, SOURCE_USER).usable:
                return item
    for item in candidates:
        if _item_connection(item, SOURCE_USER).usable:
            return item
    return None


def user_connection(
    user_id: str | None, path: str | None = None
) -> SermonAudioConnection | None:
    """The usable account a user owns, or None when they have none."""
    if not user_id:
        return None
    try:
        conn = _open(path or db_path())
    except sqlite3.Error as exc:
        logger.warning("Could not open settings database for SermonAudio lookup: %s", exc)
        return None
    try:
        blob = _blob_for_user(conn, user_id)
    except sqlite3.Error as exc:
        logger.warning("Could not read SermonAudio connection for user: %s", exc)
        return None
    finally:
        conn.close()
    item = _usable_item(blob)
    return _item_connection(item, SOURCE_USER) if item is not None else None


def any_user_connection(path: str | None = None) -> bool:
    """True when any user has stored at least one SermonAudio account."""
    try:
        conn = _open(path or db_path())
    except sqlite3.Error as exc:
        logger.warning("Could not open settings database for SermonAudio lookup: %s", exc)
        return False
    try:
        rows = conn.execute(
            "SELECT value FROM user_settings WHERE key = ?", (SETTING_KEY,)
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("Could not scan SermonAudio connections: %s", exc)
        return False
    finally:
        conn.close()
    for row in rows:
        try:
            value = json.loads(row["value"])
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and isinstance(value.get("items"), list) and value["items"]:
            return True
    return False


def bootstrap_connection() -> SermonAudioConnection:
    """The single-account fallback from the resolved app config, if usable.

    ``source`` is the winning environment variable name, ``db`` for a saved
    value, or ``default`` when nothing supplied one. An unusable fallback
    reports ``source="none"`` so the console never presents a half-configured
    connection as ready.
    """
    try:
        from ui.config_utils import resolve_config_with_sources

        config, sources = resolve_config_with_sources()
    except Exception as exc:
        logger.warning("Could not resolve SermonAudio fallback credentials: %s", exc)
        return SermonAudioConnection()
    api_key = str(config.get("api_key") or "").strip()
    broadcaster_id = str(config.get("broadcaster_id") or "").strip()
    if not api_key or not broadcaster_id:
        return SermonAudioConnection()
    return SermonAudioConnection(
        api_key=api_key,
        broadcaster_id=broadcaster_id,
        source=sources.get("api_key") or "default",
    )


def resolve_connection(
    user_id: str | None, path: str | None = None
) -> SermonAudioConnection:
    """The connection an upload by ``user_id`` will use.

    A user's own account always wins. The bootstrap fallback applies only when
    no user has stored a connection; once any account exists, a user without
    one resolves to an unusable connection and the publish is refused rather
    than borrowing someone else's credentials.
    """
    if user_id:
        own = user_connection(user_id, path)
        if own is not None and own.usable:
            return own
        if own is not None or any_user_connection(path):
            return SermonAudioConnection()
    return bootstrap_connection()


def describe(connection: SermonAudioConnection) -> dict[str, object]:
    """Public, secret-free view of a resolved connection for the console."""
    return {
        "configured": connection.usable,
        "source": connection.source,
        "account_id": connection.account_id,
        "account_name": connection.account_name,
        "broadcaster_id": connection.broadcaster_id,
        "masked_key": connection.masked_key(),
        "message": "" if connection.usable else CONNECT_ACCOUNT_MESSAGE,
    }
