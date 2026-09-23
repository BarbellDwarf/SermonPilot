"""Publish guards: never publish a sermon paused for review as raw source.

``sermon_updater.publish_dry_run_sermon`` is exercised directly with a fake
repository and mocked API calls. No network traffic and no real credentials.
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
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE sermons (
                id TEXT PRIMARY KEY, title TEXT, subtitle TEXT, speaker TEXT,
                recorded_date TEXT, event_type TEXT, bible_text TEXT,
                series_title TEXT, scripture_reference TEXT, description TEXT,
                duration INTEGER, status TEXT, edit_status TEXT, updated_at TEXT
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
            CREATE TABLE processing_info (sermon_id TEXT);
            CREATE TABLE upload_info (
                sermon_id TEXT, sermonaudio_id TEXT, upload_date TEXT,
                upload_status TEXT, upload_message TEXT
            );
            CREATE TABLE processing_status (sermon_id TEXT);
            CREATE TABLE edit_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sermon_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                proposed_start REAL,
                proposed_end REAL,
                status TEXT DEFAULT 'pending_review',
                UNIQUE(sermon_id, revision)
            );
            """
        )

    @contextmanager
    def get_connection(self):
        yield self.conn


class _Repo:
    def __init__(self, sermon: dict) -> None:
        self.sermon = sermon
        self.db = _FakeDb()

    def get_sermon(self, sermon_id: str) -> dict | None:
        if sermon_id != self.sermon.get("id"):
            return None
        data = dict(self.sermon)
        data.setdefault("content", {"description": "Test description"})
        return data


def _pending_review_metadata(tmp_path: Path) -> tuple[Path, Path]:
    """A review-directory pair: the full source and its recorded metadata."""
    source = tmp_path / "Teaching - Original.mp4"
    source.write_bytes(b"full service")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        '{"original_file": "%s", "upload_type": "original-video"}' % source,
        encoding="utf-8",
    )
    return source, metadata_path


def _pending_review_sermon(tmp_path: Path) -> tuple[dict, Path]:
    source, metadata_path = _pending_review_metadata(tmp_path)
    sermon = {
        "id": "draft_test",
        "title": "Test Title",
        "speaker": "Test Speaker",
        "recorded_date": "2024-01-01",
        "event_type": "Sunday Service",
        "status": "draft",
        "edit_status": "pending_review",
        "file_paths": {"audio": str(source), "metadata": str(metadata_path)},
        "content": {"description": "Test description", "hashtags": "#test"},
        "duration": 0,
    }
    return sermon, source


def _wire(monkeypatch, repo, tmp_path: Path) -> dict:
    import ui.database as db

    monkeypatch.setattr(db, "SermonRepository", lambda: repo)
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})
    monkeypatch.setattr(su, "resolve_speaker_id", lambda name: None)
    monkeypatch.setattr(su, "create_new_sermon_api", lambda **kwargs: "12345")
    monkeypatch.setattr(su, "set_sermon_published", lambda *args, **kwargs: True)
    monkeypatch.setattr(su, "find_sermon_dir", lambda *args, **kwargs: None)
    uploaded: dict = {}

    def fake_upload(sermon_id, path, upload_type):
        uploaded["path"] = path
        uploaded["type"] = upload_type
        return True

    monkeypatch.setattr(su, "upload_media_file", fake_upload)
    return uploaded


def test_publish_refuses_a_pending_review_draft(tmp_path: Path, monkeypatch) -> None:
    sermon, source = _pending_review_sermon(tmp_path)
    repo = _Repo(sermon)
    uploaded = _wire(monkeypatch, repo, tmp_path)

    result = su.publish_dry_run_sermon("draft_test")

    assert result["success"] is False
    assert "pending_review" in result["error"]
    assert "path" not in uploaded


def test_publish_allows_an_explicit_source_override(tmp_path: Path, monkeypatch) -> None:
    sermon, source = _pending_review_sermon(tmp_path)
    repo = _Repo(sermon)
    uploaded = _wire(monkeypatch, repo, tmp_path)

    result = su.publish_dry_run_sermon("draft_test", force_source_publish=True)

    assert result["success"] is True
    assert uploaded["path"] == str(source)
