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


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch):
    """Stop a developer's real .env from leaking into the hermetic fast suite.

    Production loads project_root/.env during config resolution. No test
    asserts that file's contents, so a no-op loader keeps the suite
    independent of the machine it runs on.
    """
    try:
        import dotenv
    except ImportError:
        return
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)


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
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    from ui.database import SermonDatabase

    SermonDatabase(db_path=str(db_path)).init_database()
    # Reset process-wide singletons so job queue + repository bind to THIS db.
    # The queue is stopped and joined rather than orphaned: dropping the
    # reference alone leaves its worker threads running into later tests.
    monkeypatch.setattr("ui.database._db", None)
    from ui.job_queue import shutdown_job_queue

    shutdown_job_queue()
    monkeypatch.setenv("SERMONPILOT_ADMIN_USER", "test-admin")
    monkeypatch.setenv("SERMONPILOT_ADMIN_PASSWORD", secrets.token_urlsafe(24))
    from fastapi.testclient import TestClient

    from server.api.app import create_app

    with TestClient(create_app()) as client:
        yield client


_UI_DIR = str(Path(__file__).resolve().parent.parent / "ui")
if _UI_DIR not in sys.path:
    sys.path.insert(0, _UI_DIR)


# --- process-wide singleton isolation ---
#
# Several modules cache a lazily-created process-wide singleton at module
# scope: the database handle (``_db``), the UI managers, and the job queue.
# A test that triggers creation through the real factory without a fixture
# to reset it leaves the handle bound for every later test, so a later test
# can bind to a stale, already-deleted temp database and fail depending on
# what ran before it. Capture the manager singletons around every test and
# restore them afterwards; each test then starts from the same clean state
# regardless of order. ``None`` is the pristine module default for every
# name listed below.
#
# ``ui.database`` is importable both as ``ui.database`` and, because the test
# suite puts ``ui/`` on ``sys.path``, as the bare ``database`` module; the two
# are distinct module objects, each with its own ``_db``. Both are watched.
#
# The job queue gets different treatment: it owns live worker threads, and
# dropping the reference does not stop them. The fixture stops and joins the
# global queue before and after every test instead, so no worker from an
# earlier test can call into a later one.
#
# Both helpers read ``sys.modules`` only: they never import a module, so they
# cannot create the very singleton they are watching. They are always on and
# have no effect on a test that leaves the singletons alone.

_PROCESS_SINGLETONS: dict[str, tuple[str, ...]] = {
    "ui.database": ("_db",),
    "database": ("_db",),
    "ui.system_status": ("_status_manager", "_status_manager_config"),
    "ui.sermon_manager": ("_sermon_manager",),
    "ui.ui_processor": ("_processor",),
    "ui.media_server": ("_server",),
    "ui.analytics_manager": ("_analytics_manager",),
}

# The job queue is not restored to its pre-test reference. A queue owns live
# worker threads, so dropping the reference while the workers keep running
# lets a previous test's job call into the next test. Every test starts and
# ends with no global queue, and any queue a test created is stopped and
# joined before the next test begins.
_JOB_QUEUE_MODULES = ("ui.job_queue", "job_queue")

_MISSING = object()


def _capture_singletons() -> dict[str, object]:
    captured: dict[str, object] = {}
    for module_name, names in _PROCESS_SINGLETONS.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name in names:
            captured[f"{module_name}.{name}"] = getattr(module, name, _MISSING)
    return captured


def _restore_singletons(captured: dict[str, object]) -> None:
    for module_name, names in _PROCESS_SINGLETONS.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name in names:
            original = captured.get(f"{module_name}.{name}", _MISSING)
            current = getattr(module, name, _MISSING)
            if original is _MISSING:
                # The module was imported during the test. Anything it cached
                # is a leak into the next test; None is its pristine default.
                if current is not None:
                    setattr(module, name, None)
            elif current is not original:
                setattr(module, name, original)


def _stop_job_queues() -> None:
    for module_name in _JOB_QUEUE_MODULES:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attr in ("_job_queue", "_submit_queue"):
            queue = getattr(module, attr, None)
            if queue is None:
                continue
            try:
                queue.stop()
            except Exception:
                pass
            setattr(module, attr, None)


@pytest.fixture(autouse=True)
def _isolate_process_singletons():
    _stop_job_queues()
    captured = _capture_singletons()
    yield
    _stop_job_queues()
    _restore_singletons(captured)


# --- global-state leak detector (diagnostic, opt-in) ---
#
# Runs before the isolation fixture sets up and reports any watched singleton
# that is already non-None when a test starts. A clean run prints nothing; any
# line names a test that began on state a previous test left behind. Inert
# unless SERMONPILOT_LEAK_CHECK is set.


def _dirty_singletons() -> list[str]:
    dirty: list[str] = []
    for module_name, names in _PROCESS_SINGLETONS.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name in names:
            value = getattr(module, name, None)
            if value is not None:
                dirty.append(f"{module_name}.{name}={value!r}")
    for module_name in _JOB_QUEUE_MODULES:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        value = getattr(module, "_job_queue", None)
        if value is not None:
            dirty.append(f"{module_name}._job_queue={value!r}")
    return dirty


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    if not os.environ.get("SERMONPILOT_LEAK_CHECK"):
        return
    dirty = _dirty_singletons()
    if dirty:
        print(f"[leak] {item.nodeid} starts with dirty singletons: " + "; ".join(dirty))
