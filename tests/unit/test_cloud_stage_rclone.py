from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

try:  # noqa: E402 - keep one module identity for ui.job_queue
    from ui.job_queue import Job, JobCancelledError, JobStatus, JobType
except ImportError:  # Streamlit entrypoint
    from job_queue import Job, JobCancelledError, JobStatus, JobType  # noqa: E402

from ui import job_executors  # noqa: E402
from ui.job_executors import execute_sermon_processing_job  # noqa: E402


def cloud_config(user_id: str) -> Path:
    from server.api.routers import cloud

    return cloud._config_path(user_id)


class _FakeProc:
    def __init__(
        self,
        args: list,
        *,
        rc: int | None = 0,
        write=None,
        lines: tuple[str, ...] = (),
        on_poll=None,
    ) -> None:
        self.args = list(args)
        self.pid = 6000
        self._rc = rc
        self.returncode: int | None = None
        self._on_poll = on_poll
        self._polls = 0
        self.terminated = False
        self.killed = False
        if write is not None:
            write(Path(self.args[3]))
        self.stdout = io.StringIO("".join(f"{line}\n" for line in lines))

    def poll(self):
        self._polls += 1
        if self._on_poll is not None:
            self._on_poll(self._polls)
        if self.terminated or self.killed:
            return self.returncode
        if self._rc is None:
            return None
        self.returncode = self._rc
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = self._rc if self._rc is not None else -15
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


def _install_fake_rclone(monkeypatch, **kwargs) -> list[_FakeProc]:
    procs: list[_FakeProc] = []

    def fake_popen(args, **_ignored):
        proc = _FakeProc(list(args), **kwargs)
        procs.append(proc)
        return proc

    monkeypatch.setattr(job_executors.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(job_executors.time, "sleep", lambda _seconds: None)
    return procs


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


def _params(source: str, **extra: Any) -> dict[str, Any]:
    form = {
        "speaker_name": "Test Speaker",
        "recorded_date": "2024-01-01",
        "event_type": "Sunday Service",
        "original_filename": "2026-09-20_09-45-58.mkv",
    }
    form.update(extra.pop("form_data", {}))
    params = {
        "uploaded_file_path": source,
        "form_data": form,
        "config": {},
    }
    params.update(extra)
    return params


@pytest.fixture
def staging(tmp_path, monkeypatch):
    root = tmp_path / "cloud_ingest"
    monkeypatch.setenv("SERMONPILOT_CLOUD_STAGING_DIR", str(root))
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    monkeypatch.delenv("SERMONPILOT_KEEP_CLOUD_STAGING", raising=False)
    monkeypatch.setattr(job_executors, "_inject_sermon_updater_config", lambda config: None)
    from server.api.routers import cloud

    monkeypatch.setattr(cloud.shutil, "which", lambda _name: "/usr/bin/rclone")
    return root


def _stub_process(monkeypatch, seen: list, result: dict[str, Any] | None = None):
    import sermon_updater

    def fake_process(**kwargs):
        path = Path(kwargs["audio_file"])
        assert path.exists(), "staged file must exist inside the pipeline"
        seen.append((path, path.read_bytes()))
        return result if result is not None else {"success": True, "sermon_id": None}

    monkeypatch.setattr(sermon_updater, "process_new_sermon", fake_process)


def test_rclone_copyto_argv_and_success(staging, monkeypatch):
    seen: list = []
    _stub_process(monkeypatch, seen)
    payload = b"fake mkv bytes"
    procs = _install_fake_rclone(
        monkeypatch, rc=0, write=lambda dest: dest.write_bytes(payload),
        lines=("Transferred: 1 MiB",),
    )

    result = execute_sermon_processing_job(
        _job(
            _params(
                "remote:gbc-data:Sermon Audio/2026-09-20_09-45-58.mkv",
                user_id="user-a",
            )
        )
    )

    assert result.success is True
    argv = procs[0].args
    assert argv[:4] == [
        "/usr/bin/rclone",
        "copyto",
        "gbc-data:Sermon Audio/2026-09-20_09-45-58.mkv",
        str(staging / "2026-09-20_09-45-58.mkv"),
    ]
    assert argv[4:6] == ["--config", str(cloud_config("user-a"))]
    assert argv[6] == "--stats-one-line"
    assert len(seen) == 1
    staged, data = seen[0]
    assert staged.name == "2026-09-20_09-45-58.mkv"
    assert data == payload
    assert not staged.exists()


def test_rclone_nonzero_exit_reports_rclone_line(staging, monkeypatch):
    seen: list = []
    _stub_process(monkeypatch, seen)
    _install_fake_rclone(
        monkeypatch, rc=2, lines=("Failed to copy: directory not found",)
    )

    result = execute_sermon_processing_job(
        _job(_params("remote:gbc-data:missing.mkv", user_id="user-a"))
    )

    assert result.success is False
    assert result.error == "cloud fetch failed: Failed to copy: directory not found"
    assert not seen
    assert list(staging.iterdir()) == []


def test_rclone_zero_byte_result_is_an_error(staging, monkeypatch):
    seen: list = []
    _stub_process(monkeypatch, seen)
    _install_fake_rclone(monkeypatch, rc=0, write=lambda dest: dest.write_bytes(b""))

    result = execute_sermon_processing_job(
        _job(_params("remote:gbc-data:empty.mkv", user_id="user-a"))
    )

    assert result.success is False
    assert result.error == "cloud fetch produced an empty file"
    assert not seen
    assert list(staging.iterdir()) == []


def test_rclone_cancel_mid_copy_kills_and_cleans_partial(staging, monkeypatch):
    seen: list = []
    _stub_process(monkeypatch, seen)
    job = _job(_params("remote:gbc-data:big.mkv", user_id="user-a"))

    def on_poll(polls: int) -> None:
        if polls >= 2:
            job.cancelled = True

    procs = _install_fake_rclone(
        monkeypatch,
        rc=None,
        write=lambda dest: dest.write_bytes(b"z" * 4096),
        on_poll=on_poll,
    )

    with pytest.raises(JobCancelledError):
        execute_sermon_processing_job(job)

    assert procs[0].terminated is True
    assert not seen
    assert list(staging.iterdir()) == []


def test_remote_without_user_id_errors_before_spawn(staging, monkeypatch):
    seen: list = []
    _stub_process(monkeypatch, seen)
    procs = _install_fake_rclone(monkeypatch, rc=0)

    result = execute_sermon_processing_job(
        _job(_params("remote:gbc-data:a.mkv"))
    )

    assert result.success is False
    assert "user id" in result.error
    assert procs == []
    assert not seen
