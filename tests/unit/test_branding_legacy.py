from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from ui import job_executors  # noqa: E402
from ui.job_queue import Job, JobStatus, JobType  # noqa: E402


def _job(params: dict) -> Job:
    return Job(
        id="job-card",
        type=JobType.SERMON_PROCESSING,
        title="New Sermon",
        description="New sermon",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters=params,
    )


def _card_params(source: str, logo_path: str) -> dict:
    return {
        "uploaded_file_path": source,
        "form_data": {
            "speaker_name": "Test Speaker",
            "recorded_date": "2024-01-01",
            "event_type": "Sunday Service",
            "logo_path": logo_path,
        },
        "config": {},
        "auto_edit_enabled": True,
        "auto_edit_mode": "interactive",
        "user_id": "user-a",
    }



def _safe_segment(user_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", user_id or "anon") or "anon"


def _branding_env(monkeypatch, tmp_path) -> Path:
    base = tmp_path / "branding"
    monkeypatch.setenv("SERMONPILOT_BRANDING_DIR", str(base))
    return base


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes(32)


def test_legacy_flat_branding_is_adopted_and_listed(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    base = _branding_env(monkeypatch, tmp_path)
    base.mkdir(parents=True)
    (base / "Full-Logo.PNG").write_bytes(_png())

    first = client.get("/api/branding", headers=s["a"]["headers"]).json()["items"]
    assert [item["name"] for item in first] == ["Full-Logo.PNG"]
    user_dir = base / _safe_segment(s["a"]["id"])
    assert first[0]["path"] == f"{user_dir.name}/Full-Logo.PNG"
    assert (user_dir / "Full-Logo.PNG").is_file()
    assert not (base / "Full-Logo.PNG").exists()

    second = client.get("/api/branding", headers=s["a"]["headers"]).json()["items"]
    assert second == first


def test_legacy_adoption_leaves_per_user_files(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    base = _branding_env(monkeypatch, tmp_path)
    base.mkdir(parents=True)
    user_dir = base / _safe_segment(s["a"]["id"])
    user_dir.mkdir(parents=True)
    (user_dir / "mine.png").write_bytes(_png())

    items = client.get("/api/branding", headers=s["a"]["headers"]).json()["items"]
    assert [item["name"] for item in items] == ["mine.png"]
    theirs = client.get("/api/branding", headers=s["b"]["headers"]).json()["items"]
    assert theirs == []


def test_legacy_name_collision_is_suffixed(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    base = _branding_env(monkeypatch, tmp_path)
    base.mkdir(parents=True)
    user_dir = base / _safe_segment(s["a"]["id"])
    user_dir.mkdir(parents=True)
    (user_dir / "card.png").write_bytes(b"existing")
    (base / "card.png").write_bytes(b"legacy")

    items = client.get("/api/branding", headers=s["a"]["headers"]).json()["items"]
    names = [item["name"] for item in items]
    assert "card.png" in names
    assert "card-1.png" in names
    assert (user_dir / "card-1.png").read_bytes() == b"legacy"
    assert (user_dir / "card.png").read_bytes() == b"existing"


def test_empty_branding_root_lists_nothing(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    _branding_env(monkeypatch, tmp_path)
    r = client.get("/api/branding", headers=s["a"]["headers"])
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_missing_ending_card_fails_job(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_BRANDING_DIR", str(tmp_path / "branding"))
    monkeypatch.setattr(job_executors, "_inject_sermon_updater_config", lambda c: None)
    src = tmp_path / "talk.mp3"
    src.write_bytes(b"ID3")

    result = job_executors.execute_sermon_processing_job(
        _job(_card_params(str(src), "ghost/card.png"))
    )

    assert result.success is False
    assert result.error == "ending card image not found"


def test_existing_ending_card_is_resolved_into_config(tmp_path, monkeypatch):
    base = tmp_path / "branding"
    (base / "user-a").mkdir(parents=True)
    (base / "user-a" / "card.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setenv("SERMONPILOT_BRANDING_DIR", str(base))
    captured: dict = {}
    monkeypatch.setattr(
        job_executors, "_inject_sermon_updater_config", lambda c: captured.update(c)
    )
    import sermon_updater

    monkeypatch.setattr(
        sermon_updater,
        "process_new_sermon",
        lambda **kwargs: {"success": True, "sermon_id": "s-1"},
    )
    src = tmp_path / "talk.mp3"
    src.write_bytes(b"ID3")

    result = job_executors.execute_sermon_processing_job(
        _job(_card_params(str(src), "user-a/card.png"))
    )

    assert result.success is True, result.error
    assert captured["auto_edit"]["logo_path"] == str(base / "user-a" / "card.png")
