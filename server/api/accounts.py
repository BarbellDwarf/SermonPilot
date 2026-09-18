from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "/data/sermon_processor.db"

USERS_DDL = """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        email TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

USER_SETTINGS_DDL = """
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id TEXT NOT NULL REFERENCES users(id),
        key TEXT NOT NULL,
        value TEXT,
        PRIMARY KEY (user_id, key)
    )
"""

SESSIONS_DDL = """
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL
    )
"""

ALL_DDL = (USERS_DDL, USER_SETTINGS_DDL, SESSIONS_DDL)


def get_db_path() -> str:
    return os.environ.get("SERMONPILOT_DB", DEFAULT_DB_PATH)


@contextmanager
def writable_conn() -> Iterator[sqlite3.Connection]:
    path = Path(get_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_columns(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    for table in ("sermons", "background_jobs"):
        if table not in tables:
            continue
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "user_id" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)")


def migrate() -> None:
    with writable_conn() as conn:
        for ddl in ALL_DDL:
            conn.execute(ddl)
        _ensure_columns(conn)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    iterations = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
    except ValueError:
        return False
    return secrets.compare_digest(digest.hex(), digest_hex)


def count_users(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def get_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user(
    conn: sqlite3.Connection,
    username: str,
    display_name: str,
    password: str,
    role: str = "user",
) -> sqlite3.Row:
    user_id = f"u-{secrets.token_hex(8)}"
    conn.execute(
        "INSERT INTO users (id, username, display_name, email, password_hash, role, is_active)"
        " VALUES (?, ?, ?, NULL, ?, ?, 1)",
        (user_id, username, display_name, hash_password(password), role),
    )
    return get_user_by_id(conn, user_id)


def create_session(conn: sqlite3.Connection, user_id: str, ttl_days: int = 7) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at)"
        " VALUES (?, ?, datetime('now', ?))",
        (token, user_id, f"+{ttl_days} days"),
    )
    return token


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_session_user(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token = ? AND s.expires_at > datetime('now') AND u.is_active = 1",
        (token,),
    ).fetchone()


def list_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, username, display_name, role, is_active, created_at"
        " FROM users ORDER BY created_at, id"
    ).fetchall()


def get_setting(conn: sqlite3.Connection, user_id: str, key: str) -> Any:
    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (user_id, key)
    ).fetchone()
    return json.loads(row["value"]) if row else None


def set_setting(conn: sqlite3.Connection, user_id: str, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
        (user_id, key, json.dumps(value)),
    )
