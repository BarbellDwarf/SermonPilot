"""Fast tests for publishing dry-run sermons to the API.

``publish_dry_run_sermon`` is exercised with a fake repository and mocked
API calls; no network traffic and no real credentials are involved.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import sermon_updater as su


class _FakeDb:
    """In-memory SQLite mirroring the tables publish_dry_run_sermon touches."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(
            """
            CREATE TABLE sermons (
                id TEXT PRIMARY KEY, title TEXT, subtitle TEXT, speaker TEXT,
                recorded_date TEXT, event_type TEXT, bible_text TEXT,
                series_title TEXT, scripture_reference TEXT, description TEXT,
                duration INTEGER, status TEXT, updated_at TEXT
            );
            CREATE TABLE sermon_files (
                sermon_id TEXT, file_type TEXT, file_path TEXT, file_size INTEGER
            );
            CREATE TABLE sermon_content (
                sermon_id TEXT, transcript_text TEXT, description TEXT,
                hashtags TEXT, key_topics TEXT, summary TEXT
            );
            CREATE TABLE sermon_search (
                sermon_id TEXT, title TEXT, speaker TEXT, transcript_text TEXT,
                description TEXT, hashtags TEXT
            );
            CREATE TABLE qa_segments (sermon_id TEXT);
            CREATE TABLE processing_info (sermon_id TEXT);
            CREATE TABLE upload_info (sermon_id TEXT);
            CREATE TABLE processing_status (sermon_id TEXT);
            """
        )

    @contextmanager
    def get_connection(self):
        yield self.conn


def _fake_repo(audio_path: Path):
    class FakeRepo:
        def __init__(self) -> None:
            self.saved = None
            self.deleted = None
            self.db = _FakeDb()

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
    fake_repo.db.conn.execute(
        "INSERT INTO sermons (id, title, status) VALUES (?, ?, ?)",
        ("draft_test", "Test Title", "draft"),
    )
    fake_repo.db.conn.commit()
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
    row = fake_repo.db.conn.execute(
        "SELECT id, status FROM sermons WHERE id = ?", ("12345",)
    ).fetchone()
    assert row is not None
    assert row[1] == "processed"
    draft_count = fake_repo.db.conn.execute(
        "SELECT COUNT(*) FROM sermons WHERE id = ?", ("draft_test",)
    ).fetchone()[0]
    assert draft_count == 0


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
