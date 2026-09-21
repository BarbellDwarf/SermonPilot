from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

try:  # noqa: E402 - keep one module identity for ui.job_queue
    from ui.job_queue import Job, JobStatus, JobType
except ImportError:  # Streamlit entrypoint
    from job_queue import Job, JobStatus, JobType  # noqa: E402

from ui import job_executors  # noqa: E402
from ui.job_executors import execute_sermon_processing_job  # noqa: E402


class _FakeProc:
    def __init__(self, rc: int = 0, lines: list[str] | None = None) -> None:
        self.returncode = rc
        self.stderr = iter(lines or [])
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout=None) -> int:
        return self.returncode

    def kill(self) -> None:
        self.terminated = True


def _job(params: dict[str, Any]) -> Job:
    return Job(
        id="job-1",
        type=JobType.SERMON_PROCESSING,
        title="New Sermon",
        description="New sermon",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters=params,
    )


def _params(source: str, output_dir: str, **extra: Any) -> dict[str, Any]:
    params = {
        "uploaded_file_path": source,
        "form_data": {
            "speaker_name": "Test Speaker",
            "recorded_date": "2024-01-01",
            "event_type": "Sunday Service",
        },
        "config": {},
        "output_dir": output_dir,
        "user_id": "user-a",
        "sermon_id": "s-1",
    }
    params.update(extra)
    return params


def _stub_pipeline(monkeypatch, captured: dict, payload: bytes = b"audio") -> list:
    seen: list[Path] = []
    monkeypatch.setattr(
        job_executors, "_inject_sermon_updater_config", lambda c: captured.update(c)
    )

    def fake_process(**kwargs):
        out = Path(captured["output_directory"])
        out.mkdir(parents=True, exist_ok=True)
        (out / "sermon.mp3").write_bytes(payload)
        seen.append(out)
        return {"success": True, "sermon_id": "s-1", "output_dir": str(out)}

    import sermon_updater

    monkeypatch.setattr(sermon_updater, "process_new_sermon", fake_process)
    return seen


@pytest.fixture
def cloud_env(tmp_path, monkeypatch):
    staging = tmp_path / "cloud_output"
    rclone = tmp_path / "rclone"
    monkeypatch.setenv("SERMONPILOT_CLOUD_OUTPUT_DIR", str(staging))
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(rclone))
    from server.api.routers import cloud

    monkeypatch.setattr(cloud.shutil, "which", lambda _name: "/usr/bin/rclone")
    return {"staging": staging, "rclone": rclone}


def test_remote_output_stages_uploads_and_records(tmp_path, cloud_env, monkeypatch):
    captured: dict = {}
    _stub_pipeline(monkeypatch, captured)
    calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        calls.append(list(cmd))
        return _FakeProc(
            rc=0,
            lines=[
                "Transferred: 1 MiB / 2 MiB, 50%, 1 MiB/s, ETA 1s",
                "Transferred: 2 MiB / 2 MiB, 100%",
            ],
        )

    monkeypatch.setattr(job_executors.subprocess, "Popen", fake_popen)
    src = tmp_path / "talk.mp3"
    src.write_bytes(b"ID3")

    result = execute_sermon_processing_job(
        _job(_params(str(src), "remote:drive:talks"))
    )

    assert result.success is True, result.error
    assert result.data["output_dir"] == "drive:talks"
    assert result.data["cloud_output"] == "drive:talks"
    assert calls and calls[0][0] == "/usr/bin/rclone"
    assert "copy" in calls[0]
    assert "drive:talks" in calls[0]
    staged = captured["output_directory"]
    assert calls[0][calls[0].index("copy") + 1] == staged
    assert not Path(staged).exists(), "staging dir must be deleted after verified upload"


def test_remote_output_failure_uses_rclone_error(tmp_path, cloud_env, monkeypatch):
    captured: dict = {}
    _stub_pipeline(monkeypatch, captured)
    last = "ERROR : Fatal error: could not create directory"
    monkeypatch.setattr(
        job_executors.subprocess,
        "Popen",
        lambda cmd, **kw: _FakeProc(rc=1, lines=["Transferred: 0 B / 2 MiB, 0%", last]),
    )
    src = tmp_path / "talk.mp3"
    src.write_bytes(b"ID3")

    result = execute_sermon_processing_job(
        _job(_params(str(src), "remote:drive:talks"))
    )

    assert result.success is False
    assert "cloud output failed" in result.error
    assert last in result.error
    assert Path(captured["output_directory"]).exists(), "staging kept on failure"


def test_local_output_unchanged(tmp_path, monkeypatch):
    captured: dict = {}
    _stub_pipeline(monkeypatch, captured)
    uploads: list = []
    monkeypatch.setattr(
        job_executors, "_upload_cloud_output", lambda *a, **k: uploads.append(a)
    )
    outdir = tmp_path / "processed"
    src = tmp_path / "talk.mp3"
    src.write_bytes(b"ID3")

    result = execute_sermon_processing_job(_job(_params(str(src), str(outdir))))

    assert result.success is True
    assert captured["output_directory"] == str(outdir)
    assert uploads == []
    assert (outdir / "sermon.mp3").is_file()


def _write_remote_config(rclone_dir: Path, user_id: str, name: str = "drive") -> None:
    import re

    safe = re.sub(r"[^A-Za-z0-9_-]", "_", user_id or "anon") or "anon"
    cfg = rclone_dir / safe / "config"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(f"[{name}]\ntype = drive\n", encoding="utf-8")


def test_output_dir_accepts_configured_remote(client, scoped_setup, cloud_env):
    s = scoped_setup
    _write_remote_config(cloud_env["rclone"], s["a"]["id"])
    r = client.put(
        "/api/me/output-dir",
        json={"output_dir": "remote:drive:talks/2026"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["output_dir"] == "remote:drive:talks/2026"
    got = client.get("/api/me/output-dir", headers=s["a"]["headers"]).json()
    assert got["output_dir"] == "remote:drive:talks/2026"


def test_output_dir_rejects_unknown_remote(client, scoped_setup, cloud_env):
    s = scoped_setup
    r = client.put(
        "/api/me/output-dir",
        json={"output_dir": "remote:ghost:talks"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 422
    assert "ghost" in r.json()["detail"]


def test_server_path_job_keeps_remote_output(client, scoped_setup, cloud_env, tmp_path):
    s = scoped_setup
    _write_remote_config(cloud_env["rclone"], s["a"]["id"])
    src = tmp_path / "talk.mp3"
    src.write_bytes(b"ID3")
    r = client.post(
        "/api/sermons/server-path",
        json={
            "container_path": str(src),
            "title": "Talk",
            "speaker": "Speaker A",
            "recorded_date": "2026-09-14",
            "output_dir": "remote:drive:talks",
        },
        headers=s["a"]["headers"],
    )
    assert r.status_code == 201, r.text
    import json
    import sqlite3

    from server.api.accounts import get_db_path

    conn = sqlite3.connect(get_db_path())
    params = json.loads(
        conn.execute(
            "SELECT parameters FROM background_jobs WHERE id = ?", (r.json()["job_id"],)
        ).fetchone()[0]
    )
    conn.close()
    assert params["output_dir"] == "remote:drive:talks"
