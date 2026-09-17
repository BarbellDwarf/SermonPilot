"""Shared test fixtures and environment setup.

The fast suite runs without network, audio, or GPU resources.  This module
points the app at a throwaway config and database, stubs optional
third-party modules, and skips tests marked ``heavy`` unless ``--run-heavy``
is passed.
"""

from __future__ import annotations

import os
import secrets
import sys
import tempfile
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_TMP_DIR = Path(tempfile.mkdtemp(prefix="sermonpilot-tests-"))
_CONFIG_PATH = _TMP_DIR / "config.yaml"
_CONFIG_PATH.write_text(
    "api_key: test-api-key\nbroadcaster_id: test-broadcaster\noutput_directory: test_output\n",
    encoding="utf-8",
)
os.environ["SA_UPDATER_CONFIG"] = str(_CONFIG_PATH)
os.environ["DATABASE_URL"] = str(_TMP_DIR / "test.db")


def _stub_sermonaudio() -> None:
    stub = types.ModuleType("sermonaudio")
    stub.set_api_key = lambda key: None
    node = types.ModuleType("sermonaudio.node")
    requests_mod = types.ModuleType("sermonaudio.node.requests")
    requests_mod.Node = None
    node.requests = requests_mod
    stub.node = node
    sys.modules["sermonaudio"] = stub
    sys.modules["sermonaudio.node"] = node
    sys.modules["sermonaudio.node.requests"] = requests_mod


try:
    import sermonaudio  # noqa: F401
except ImportError:
    _stub_sermonaudio()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-heavy",
        action="store_true",
        default=False,
        help="Run heavy tests that need network, audio, or GPU resources",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-heavy"):
        return
    skip_heavy = pytest.mark.skip(reason="requires network, audio, or GPU; use --run-heavy")
    for item in items:
        if "heavy" in item.keywords:
            item.add_marker(skip_heavy)



# --- SermonPilot API fixtures (shared by accounts + settings tests) ---

JOBS_DDL = """
    CREATE TABLE IF NOT EXISTS background_jobs (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL,
        progress REAL DEFAULT 0,
        parameters TEXT,
        result TEXT,
        logs TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        can_cancel BOOLEAN DEFAULT 1,
        can_retry BOOLEAN DEFAULT 1,
        priority INTEGER DEFAULT 5,
        user_id TEXT
    )
"""

@pytest.fixture
def scoped_setup(client):
    from server.api.accounts import migrate

    migrate()
    admin_pw = os.environ["SERMONPILOT_ADMIN_PASSWORD"]
    client.post("/api/auth/bootstrap")
    admin_token = client.post(
        "/api/auth/login", json={"username": "test-admin", "password": admin_pw}
    ).json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = client.get("/api/auth/me", headers=admin_headers).json()["id"]

    def make_user(username: str) -> dict:
        body = {
            "username": username,
            "display_name": username,
            "password": "pw-" + username,
            "role": "user",
        }
        user = client.post("/api/admin/users", json=body, headers=admin_headers).json()
        token = client.post(
            "/api/auth/login", json={"username": username, "password": "pw-" + username}
        ).json()["token"]
        return {"id": user["id"], "headers": {"Authorization": f"Bearer {token}"}}

    user_a = make_user("user-a")
    user_b = make_user("user-b")
    import sqlite3

    from server.api.accounts import get_db_path

    sermon_insert = (
        "INSERT INTO sermons (id, title, speaker, recorded_date, status, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?)"
    )
    job_insert = (
        "INSERT INTO background_jobs (id, type, title, status, user_id) VALUES (?, ?, ?, ?, ?)"
    )
    conn = sqlite3.connect(get_db_path())
    conn.execute(JOBS_DDL)
    conn.execute(
        sermon_insert, ("s-a", "Owned A", "Speaker A", "2026-09-01", "processed", user_a["id"])
    )
    conn.execute(
        sermon_insert, ("s-b", "Owned B", "Speaker B", "2026-09-02", "processed", user_b["id"])
    )
    conn.execute(
        sermon_insert, ("s-null", "Legacy", "Speaker C", "2026-09-03", "processed", None)
    )
    for jid, owner in (("j-a", user_a["id"]), ("j-b", user_b["id"]), ("j-null", None)):
        conn.execute(job_insert, (jid, "full_pipeline", jid, "completed", owner))
    conn.commit()
    conn.close()
    return {"admin_headers": admin_headers, "admin_id": admin_id, "a": user_a, "b": user_b}




@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "accounts.db"
    monkeypatch.setenv("SERMONPILOT_DB", str(db_path))
    from ui.database import SermonDatabase

    SermonDatabase(db_path=str(db_path)).init_database()
    monkeypatch.setenv("SERMONPILOT_ADMIN_USER", "test-admin")
    monkeypatch.setenv("SERMONPILOT_ADMIN_PASSWORD", secrets.token_urlsafe(24))
    from fastapi.testclient import TestClient

    from server.api.app import create_app

    with TestClient(create_app()) as client:
        yield client


_UI_DIR = str(Path(__file__).resolve().parent.parent / "ui")
if _UI_DIR not in sys.path:
    sys.path.insert(0, _UI_DIR)
