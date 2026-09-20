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
    from ui.job_queue import Job, JobCancelledError, JobStatus, JobType
except ImportError:  # Streamlit entrypoint
    from job_queue import Job, JobCancelledError, JobStatus, JobType  # noqa: E402

from ui import job_executors  # noqa: E402
from ui.job_executors import execute_sermon_processing_job  # noqa: E402


class _FakeResponse:
    def __init__(self, data: bytes, on_read=None) -> None:
        self._data = data
        self._pos = 0
        self.headers = {"Content-Length": str(len(data))}
        self._on_read = on_read

    def read(self, size: int = -1) -> bytes:
        if self._on_read is not None:
            self._on_read()
            self._on_read = None
        if self._pos >= len(self._data):
            return b""
        end = self._pos + size if size and size > 0 else len(self._data)
        chunk = self._data[self._pos:end]
        self._pos += len(chunk)
        return chunk

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


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
    monkeypatch.delenv("SERMONPILOT_KEEP_CLOUD_STAGING", raising=False)
    monkeypatch.setattr(job_executors, "_inject_sermon_updater_config", lambda config: None)
    return root


def _stub_process(monkeypatch, seen: list[str], result: dict[str, Any] | None = None):
    import sermon_updater

    def fake_process(**kwargs):
        path = Path(kwargs["audio_file"])
        assert path.exists(), "staged file must exist inside the pipeline"
        seen.append((path, path.read_bytes()))
        return result if result is not None else {"success": True, "sermon_id": None}

    monkeypatch.setattr(sermon_updater, "process_new_sermon", fake_process)


def test_http_url_is_staged_then_processed(staging, monkeypatch):
    seen: list[str] = []
    _stub_process(monkeypatch, seen)
    payload = b"fake audio bytes"
    monkeypatch.setattr(job_executors, "_open_url", lambda url: _FakeResponse(payload))

    result = execute_sermon_processing_job(
        _job(_params("http://127.0.0.1:9999/talks/a.mkv"))
    )

    assert result.success is True
    assert len(seen) == 1
    staged, data = seen[0]
    assert staged.name == "a.mkv"
    assert staged.parent == staging
    assert data == payload
    assert not staged.exists()


def test_http_url_failure_leaves_no_partial(staging, monkeypatch):
    seen: list[str] = []
    _stub_process(monkeypatch, seen)

    def boom(url):
        raise RuntimeError("404 Not Found")

    monkeypatch.setattr(job_executors, "_open_url", boom)

    result = execute_sermon_processing_job(
        _job(_params("http://127.0.0.1:9999/talks/missing.mkv"))
    )

    assert result.success is False
    assert "cloud fetch" in result.error
    assert not seen
    assert list(staging.iterdir()) == []


def test_staged_file_removed_after_successful_run(staging, monkeypatch):
    seen: list[str] = []
    _stub_process(monkeypatch, seen)
    monkeypatch.setattr(
        job_executors, "_open_url", lambda url: _FakeResponse(b"x" * 4096)
    )

    execute_sermon_processing_job(_job(_params("http://127.0.0.1:9999/talks/a.wav")))

    assert list(staging.iterdir()) == []


def test_cancel_mid_download_cleans_partial(staging, monkeypatch):
    seen: list[str] = []
    _stub_process(monkeypatch, seen)
    job = _job(_params("http://127.0.0.1:9999/talks/big.wav"))

    def cancel_after_first_read():
        job.cancelled = True

    monkeypatch.setattr(
        job_executors,
        "_open_url",
        lambda url: _FakeResponse(b"y" * (3 * 1024 * 1024), on_read=cancel_after_first_read),
    )

    with pytest.raises(JobCancelledError):
        execute_sermon_processing_job(job)

    assert list(staging.iterdir()) == []


def test_remote_string_without_user_id_errors_clearly(staging, monkeypatch):
    seen: list[str] = []
    _stub_process(monkeypatch, seen)

    result = execute_sermon_processing_job(
        _job(_params("remote:mine:/talks/a.mp3"))
    )

    assert result.success is False
    assert "user id" in result.error
    assert not seen
