"""Fast tests for publishing dry-run sermons to the API.

``publish_dry_run_sermon`` is exercised with a fake repository and mocked
API calls; no network traffic and no real credentials are involved.
"""

from __future__ import annotations

from pathlib import Path

import sermon_updater as su


def _fake_repo(audio_path: Path):
    class FakeRepo:
        def __init__(self) -> None:
            self.saved = None
            self.deleted = None

        def get_sermon(self, sermon_id: str) -> dict:
            return {
                "title": "Test Title",
                "speaker": "Test Speaker",
                "recorded_date": "2024-01-01",
                "event_type": "Sunday Service",
                "content": {
                    "description": "Test description",
                    "hashtags": "#test",
                    "transcript_text": "transcript",
                },
                "file_paths": {"audio": str(audio_path), "metadata": ""},
                "duration": 0,
            }

        def save_sermon(self, data: dict) -> None:
            self.saved = data

        def delete_sermon(self, sermon_id: str) -> None:
            self.deleted = sermon_id

    return FakeRepo()


def test_publish_dry_run_sermon_creates_and_uploads(tmp_path: Path, monkeypatch) -> None:
    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")

    import ui.database as db

    fake_repo = _fake_repo(audio_file)
    monkeypatch.setattr(db, "SermonRepository", lambda: fake_repo)
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})
    monkeypatch.setattr(su, "resolve_speaker_id", lambda name: None)
    monkeypatch.setattr(su, "create_new_sermon_api", lambda **kwargs: "12345")
    monkeypatch.setattr(su, "upload_media_file", lambda *args, **kwargs: True)
    monkeypatch.setattr(su, "find_sermon_dir", lambda *args, **kwargs: None)

    result = su.publish_dry_run_sermon("draft_test")

    assert result["success"] is True
    assert result["sermon_id"] == "12345"
    assert result["error"] is None
    assert fake_repo.saved["id"] == "12345"
    assert fake_repo.saved["status"] == "processed"
    assert fake_repo.deleted == "draft_test"


def test_publish_dry_run_sermon_create_failure(tmp_path: Path, monkeypatch) -> None:
    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")

    import ui.database as db

    fake_repo = _fake_repo(audio_file)
    monkeypatch.setattr(db, "SermonRepository", lambda: fake_repo)
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})
    monkeypatch.setattr(su, "resolve_speaker_id", lambda name: None)
    monkeypatch.setattr(su, "create_new_sermon_api", lambda **kwargs: None)
    monkeypatch.setattr(su, "find_sermon_dir", lambda *args, **kwargs: None)

    result = su.publish_dry_run_sermon("draft_test")

    assert result["success"] is False
    assert "Failed to create sermon" in result["error"]


def test_publish_dry_run_sermon_missing_sermon_returns_error(monkeypatch) -> None:
    import ui.database as db

    class EmptyRepo:
        def get_sermon(self, sermon_id: str):
            return None

    monkeypatch.setattr(db, "SermonRepository", lambda: EmptyRepo())

    result = su.publish_dry_run_sermon("draft_missing")

    assert result["success"] is False
    assert "not found" in result["error"]


def test_publish_dry_run_sermon_missing_audio_returns_error(tmp_path: Path, monkeypatch) -> None:
    import ui.database as db

    class Repo:
        def get_sermon(self, sermon_id: str) -> dict:
            return {
                "title": "Test Title",
                "speaker": "Test Speaker",
                "recorded_date": "2024-01-01",
                "content": {},
                "file_paths": {"audio": str(tmp_path / "missing.mp3")},
            }

    monkeypatch.setattr(db, "SermonRepository", lambda: Repo())
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})
    monkeypatch.setattr(su, "find_sermon_dir", lambda *args, **kwargs: None)

    result = su.publish_dry_run_sermon("draft_test")

    assert result["success"] is False
    assert "not found" in result["error"]
