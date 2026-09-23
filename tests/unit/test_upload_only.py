"""Upload-only routing: publish the stored render without re-rendering.

The guard is exercised through the API (refusals happen before a job exists)
and through the executor (a refusal never falls back to the render pipeline).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from ui.job_queue import Job, JobStatus, JobType  # noqa: E402


class _FakeRepo:
    def __init__(self, sermon: dict) -> None:
        self.sermon = sermon

    def get_sermon(self, sermon_id: str) -> dict | None:
        if sermon_id == self.sermon.get("id"):
            return self.sermon
        return None


def _rendered_sermon(tmp_path: Path, **overrides) -> dict:
    render = tmp_path / "Teaching One - Processed.mp3"
    render.write_bytes(b"rendered bytes")
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"processed_file": str(render)}), encoding="utf-8")
    sermon = {
        "id": "s-rendered",
        "title": "Teaching One",
        "speaker": "Speaker One",
        "recorded_date": "2026-09-01",
        "status": "draft",
        "edit_status": "rendered",
        "file_paths": {"audio": str(render), "metadata": str(metadata)},
        "content": {"description": "A generated description.", "hashtags": "#tag"},
        "upload_info": {},
    }
    sermon.update(overrides)
    return sermon


def _publish_job(sermon_id: str, *, upload_only: bool = True, confirm: bool = False) -> Job:
    return Job(
        id="job-publish-1",
        type=JobType.SERMON_PUBLISH,
        title="Upload",
        description="Upload",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters={
            "sermon_id": sermon_id,
            "upload_only": upload_only,
            "confirm_missing_description": confirm,
        },
    )


def test_upload_only_uses_stored_render_and_skips_pipeline(tmp_path, monkeypatch) -> None:
    sermon = _rendered_sermon(tmp_path)
    repo = _FakeRepo(sermon)
    uploader = Mock(return_value={"success": True, "sermon_id": "12345", "error": None})
    process = Mock(side_effect=AssertionError("render must not run"))
    detect = Mock(side_effect=AssertionError("cut detection must not run"))
    apply_core = Mock(side_effect=AssertionError("apply core must not run"))
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    monkeypatch.setattr("sermon_updater.detect_cut_points", detect)
    monkeypatch.setattr("ui.auto_edit_apply.run_library_apply", apply_core)

    from ui.upload_only import run_upload_existing

    messages: list[str] = []
    result = run_upload_existing(
        repo,
        "s-rendered",
        uploader=uploader,
        progress_callback=lambda _pct, msg: messages.append(msg),
    )

    assert result["success"] is True
    assert result["sermon_id"] == "12345"
    assert uploader.call_args.kwargs["upload_path"] == str(
        sermon["file_paths"]["audio"]
    )
    assert any("Uploading the existing render for" in msg for msg in messages)
    assert any("Teaching One - Processed.mp3" in msg for msg in messages)
    process.assert_not_called()
    detect.assert_not_called()
    apply_core.assert_not_called()


def test_upload_only_without_a_render_refuses_and_does_not_render(tmp_path, monkeypatch) -> None:
    sermon = _rendered_sermon(tmp_path)
    sermon["file_paths"] = {"audio": str(tmp_path / "missing.mp3"), "metadata": ""}
    sermon["edit_status"] = "draft"
    repo = _FakeRepo(sermon)
    uploader = Mock()
    process = Mock(side_effect=AssertionError("render must not run"))
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)

    from ui.upload_only import run_upload_existing

    result = run_upload_existing(repo, "s-rendered", uploader=uploader)

    assert result["success"] is False
    assert result["error_code"] == "no_render"
    assert "No rendered output" in result["error"]
    uploader.assert_not_called()
    process.assert_not_called()


def test_upload_only_refuses_an_already_published_sermon(tmp_path) -> None:
    sermon = _rendered_sermon(
        tmp_path,
        status="processed",
        edit_status="uploaded",
        upload_info={"sermonaudio_id": "999"},
    )
    repo = _FakeRepo(sermon)
    uploader = Mock()

    from ui.upload_only import run_upload_existing

    result = run_upload_existing(repo, "s-rendered", uploader=uploader)

    assert result["success"] is False
    assert result["error_code"] == "already_published"
    assert "already published" in result["error"]
    assert "999" in result["error"]
    uploader.assert_not_called()


def test_upload_only_refuses_empty_description_until_confirmed(tmp_path) -> None:
    sermon = _rendered_sermon(tmp_path)
    sermon["content"] = {"description": "", "hashtags": ""}
    repo = _FakeRepo(sermon)
    uploader = Mock(return_value={"success": True, "sermon_id": "12345", "error": None})

    from ui.upload_only import run_upload_existing

    refused = run_upload_existing(repo, "s-rendered", uploader=uploader)
    assert refused["success"] is False
    assert refused["error_code"] == "missing_description"
    assert refused["can_regenerate"] is True
    assert "Regenerate the description" in refused["error"]
    uploader.assert_not_called()

    confirmed = run_upload_existing(
        repo, "s-rendered", confirm_missing_description=True, uploader=uploader
    )
    assert confirmed["success"] is True
    assert uploader.call_args.kwargs["upload_path"] == str(
        sermon["file_paths"]["audio"]
    )


def test_publish_executor_routes_upload_only_to_the_stored_render(tmp_path, monkeypatch) -> None:
    sermon = _rendered_sermon(tmp_path)
    repo = _FakeRepo(sermon)
    monkeypatch.setattr("ui.database.SermonRepository", lambda *a, **k: repo)
    uploader = Mock(return_value={"success": True, "sermon_id": "12345", "error": None})
    monkeypatch.setattr("sermon_updater.publish_dry_run_sermon", uploader)
    process = Mock(side_effect=AssertionError("render must not run"))
    detect = Mock(side_effect=AssertionError("cut detection must not run"))
    apply_core = Mock(side_effect=AssertionError("apply core must not run"))
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)
    monkeypatch.setattr("sermon_updater.detect_cut_points", detect)
    monkeypatch.setattr("ui.auto_edit_apply.run_library_apply", apply_core)

    from ui.job_executors import execute_sermon_publish_job

    result = execute_sermon_publish_job(_publish_job("s-rendered"))

    assert result.success is True
    assert uploader.call_args.kwargs["upload_path"] == str(
        sermon["file_paths"]["audio"]
    )
    assert "Teaching One - Processed.mp3" in result.message
    process.assert_not_called()
    detect.assert_not_called()
    apply_core.assert_not_called()


def test_publish_executor_upload_only_refusal_is_documented(tmp_path, monkeypatch) -> None:
    sermon = _rendered_sermon(tmp_path)
    sermon["file_paths"] = {"audio": str(tmp_path / "missing.mp3"), "metadata": ""}
    sermon["edit_status"] = "draft"
    repo = _FakeRepo(sermon)
    monkeypatch.setattr("ui.database.SermonRepository", lambda *a, **k: repo)
    uploader = Mock()
    monkeypatch.setattr("sermon_updater.publish_dry_run_sermon", uploader)

    from ui.job_executors import execute_sermon_publish_job

    result = execute_sermon_publish_job(_publish_job("s-rendered"))

    assert result.success is False
    assert result.data and result.data.get("error_code") == "no_render"
    uploader.assert_not_called()


# --- API surface ---------------------------------------------------------


def _seed_rendered_sermon(
    tmp_path: Path,
    user_id: str,
    *,
    description: str = "A generated description.",
    status: str = "draft",
    edit_status: str = "rendered",
    remote_id: str | None = None,
) -> dict:
    from server.api.accounts import get_db_path

    render = tmp_path / "Teaching R - Processed.mp3"
    render.write_bytes(b"rendered bytes")
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"processed_file": str(render)}), encoding="utf-8")
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT OR REPLACE INTO sermons"
        " (id, title, speaker, recorded_date, status, edit_status, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("s-r", "Rendered One", "Speaker R", "2026-09-05", status, edit_status, user_id),
    )
    for file_type, path in (("audio", render), ("metadata", metadata)):
        conn.execute(
            "INSERT OR REPLACE INTO sermon_files (sermon_id, file_type, file_path, file_size)"
            " VALUES (?, ?, ?, ?)",
            ("s-r", file_type, str(path), path.stat().st_size),
        )
    conn.execute(
        "INSERT OR REPLACE INTO sermon_content"
        " (sermon_id, description, hashtags, transcript_text) VALUES (?, ?, ?, ?)",
        ("s-r", description, "#tag", "text"),
    )
    if remote_id:
        conn.execute(
            "INSERT OR REPLACE INTO upload_info (sermon_id, sermonaudio_id, upload_status)"
            " VALUES (?, ?, ?)",
            ("s-r", remote_id, "completed"),
        )
    conn.commit()
    conn.close()
    return {"render": render}


@pytest.fixture(autouse=True)
def _no_worker(monkeypatch):
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)


def test_api_upload_only_queues_publish_job(client, scoped_setup, tmp_path) -> None:
    s = scoped_setup
    seeded = _seed_rendered_sermon(tmp_path, s["a"]["id"])

    r = client.post(
        "/api/sermons/s-r/plan/apply",
        json={"upload_only": True},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["render"]["name"] == seeded["render"].name

    from server.api.accounts import get_db_path

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT type, user_id, parameters FROM background_jobs WHERE id = ?",
        (body["job_id"],),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "sermon_publish"
    assert row[1] == s["a"]["id"]
    params = json.loads(row[2])
    assert params["upload_only"] is True
    assert params["sermon_id"] == "s-r"


def test_api_upload_only_without_render_returns_no_render(client, scoped_setup) -> None:
    s = scoped_setup
    created = client.post(
        "/api/sermons",
        json={"title": "No Render", "speaker": "S", "recorded_date": "2026-09-06"},
        headers=s["a"]["headers"],
    ).json()

    r = client.post(
        f"/api/sermons/{created['id']}/plan/apply",
        json={"upload_only": True},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "no_render"
    assert "No rendered output" in detail["message"]


def test_api_upload_only_on_published_sermon_returns_conflict(
    client, scoped_setup, tmp_path
) -> None:
    s = scoped_setup
    _seed_rendered_sermon(
        tmp_path,
        s["a"]["id"],
        status="processed",
        edit_status="uploaded",
        remote_id="777",
    )

    r = client.post(
        "/api/sermons/s-r/plan/apply",
        json={"upload_only": True},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "already_published"
    assert "777" in detail["message"]


def test_api_upload_only_while_a_job_is_active_returns_conflict(
    client, scoped_setup, tmp_path
) -> None:
    s = scoped_setup
    _seed_rendered_sermon(tmp_path, s["a"]["id"])
    from server.api.accounts import get_db_path

    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO background_jobs (id, type, title, status, parameters, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            "j-active",
            "auto_edit_apply",
            "Apply edit",
            "running",
            json.dumps({"sermon_id": "s-r"}),
            s["a"]["id"],
        ),
    )
    conn.commit()
    conn.close()

    r = client.post(
        "/api/sermons/s-r/plan/apply",
        json={"upload_only": True},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "job_active"
    assert detail["job_id"] == "j-active"


def test_api_upload_only_missing_description_needs_confirmation(
    client, scoped_setup, tmp_path
) -> None:
    s = scoped_setup
    _seed_rendered_sermon(tmp_path, s["a"]["id"], description="")

    refused = client.post(
        "/api/sermons/s-r/plan/apply",
        json={"upload_only": True},
        headers=s["a"]["headers"],
    )
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "missing_description"
    assert detail["can_regenerate"] is True
    assert "Regenerate the description" in detail["message"]

    confirmed = client.post(
        "/api/sermons/s-r/plan/apply",
        json={"upload_only": True, "confirm_missing_description": True},
        headers=s["a"]["headers"],
    )
    assert confirmed.status_code == 202, confirmed.text


def test_api_upload_only_is_scoped_to_the_owner(client, scoped_setup, tmp_path) -> None:
    s = scoped_setup
    _seed_rendered_sermon(tmp_path, s["a"]["id"])

    r = client.post(
        "/api/sermons/s-r/plan/apply",
        json={"upload_only": True},
        headers=s["b"]["headers"],
    )
    assert r.status_code == 404
