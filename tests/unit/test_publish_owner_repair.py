"""Ownership survives a draft publish, and NULL owners can be healed.

The publish path migrates a draft row to its SermonAudio id. These tests pin
that the migration carries the draft's ownership/identity fields and that the
owner check accepts the published row, plus the idempotent repair that assigns
a NULL owner from a recorded publish job when that is unambiguous.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import sermon_updater as su
from ui.database import SermonDatabase, repair_ownerless_sermons


@pytest.fixture(autouse=True)
def _no_worker(monkeypatch):
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_publish_migrates_owner_and_owner_can_write(
    client, scoped_setup, tmp_path, monkeypatch
) -> None:
    from server.api.accounts import get_db_path

    s = scoped_setup
    owner = s["a"]["id"]
    other = s["b"]["id"]

    audio = tmp_path / "sermon.mp3"
    audio.write_bytes(b"audio bytes")
    source = tmp_path / "source.wav"
    source.write_bytes(b"source bytes")

    conn = _connect(get_db_path())
    conn.execute(
        "INSERT INTO sermons"
        " (id, title, speaker, recorded_date, event_type, status, user_id,"
        "  notes, church_name, is_favorite, description_needs_review)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "draft_owner",
            "Owned Draft",
            "Speaker One",
            "2026-09-01",
            "Sunday Service",
            "draft",
            owner,
            "keep this note",
            "Placeholder Church",
            1,
            1,
        ),
    )
    for file_type, path in (("audio", audio), ("original_audio", source)):
        conn.execute(
            "INSERT OR REPLACE INTO sermon_files (sermon_id, file_type, file_path, file_size)"
            " VALUES (?, ?, ?, ?)",
            ("draft_owner", file_type, str(path), path.stat().st_size),
        )
    conn.execute(
        "INSERT OR REPLACE INTO sermon_content"
        " (sermon_id, transcript_text, description, hashtags, key_topics, summary)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            "draft_owner",
            "transcript",
            "a description",
            "#tag",
            json.dumps(["topic-a"]),
            "a summary",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})
    monkeypatch.setattr(su, "resolve_speaker_id", lambda name: None)
    monkeypatch.setattr(su, "create_new_sermon_api", lambda **kwargs: "92326248567389")
    monkeypatch.setattr(su, "upload_media_file", lambda *args, **kwargs: True)
    monkeypatch.setattr(su, "find_sermon_dir", lambda *args, **kwargs: None)

    result = su.publish_dry_run_sermon("draft_owner")

    assert result["success"] is True
    new_id = result["sermon_id"]
    assert new_id == "92326248567389"

    conn = _connect(get_db_path())
    row = conn.execute(
        "SELECT user_id, notes, church_name, is_favorite,"
        " description_needs_review, recorded_date, created_at"
        " FROM sermons WHERE id = ?",
        (new_id,),
    ).fetchone()
    assert row is not None
    assert row["user_id"] == owner
    assert row["notes"] == "keep this note"
    assert row["church_name"] == "Placeholder Church"
    assert row["is_favorite"] == 1
    assert row["description_needs_review"] == 1
    assert row["recorded_date"] == "2026-09-01"

    files = {
        r["file_type"]: r["file_path"]
        for r in conn.execute(
            "SELECT file_type, file_path FROM sermon_files WHERE sermon_id = ?", (new_id,)
        )
    }
    assert files["original_audio"] == str(source)
    assert files["audio"] == str(audio)

    content = conn.execute(
        "SELECT key_topics, summary FROM sermon_content WHERE sermon_id = ?", (new_id,)
    ).fetchone()
    assert json.loads(content["key_topics"]) == ["topic-a"]
    assert content["summary"] == "a summary"

    draft_gone = conn.execute(
        "SELECT COUNT(*) FROM sermons WHERE id = ?", ("draft_owner",)
    ).fetchone()[0]
    conn.close()
    assert draft_gone == 0

    from server.api.routers.writes import _sermon_owner

    assert _sermon_owner(new_id) == owner

    ok = client.post(f"/api/sermons/{new_id}/upload", headers=s["a"]["headers"])
    assert ok.status_code == 202, ok.text
    denied = client.post(f"/api/sermons/{new_id}/upload", headers=s["b"]["headers"])
    assert denied.status_code == 404, denied.text
    assert other != owner


def _owner_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sermons (id TEXT PRIMARY KEY, user_id TEXT);
        CREATE TABLE background_jobs (
            id TEXT PRIMARY KEY, type TEXT, result TEXT, user_id TEXT
        );
        """
    )
    return conn


def test_repair_assigns_owner_from_publish_record_and_is_idempotent() -> None:
    conn = _owner_db()
    conn.execute("INSERT INTO sermons (id, user_id) VALUES ('s-published', NULL)")
    conn.execute("INSERT INTO sermons (id, user_id) VALUES ('s-owned', 'u-keeper')")
    conn.execute(
        "INSERT INTO background_jobs (id, type, result, user_id) VALUES (?, ?, ?, ?)",
        (
            "j-publish",
            "sermon_publish",
            json.dumps({"success": True, "data": {"sermon_id": "s-published"}}),
            "u-owner",
        ),
    )
    conn.commit()

    first = repair_ownerless_sermons(conn)
    assert first["repaired"] == [{"sermon_id": "s-published", "user_id": "u-owner"}]
    assert first["unresolved"] == []
    assert conn.execute(
        "SELECT user_id FROM sermons WHERE id = 's-published'"
    ).fetchone()[0] == "u-owner"
    assert conn.execute(
        "SELECT user_id FROM sermons WHERE id = 's-owned'"
    ).fetchone()[0] == "u-keeper"

    second = repair_ownerless_sermons(conn)
    assert second == {"repaired": [], "unresolved": []}
    conn.close()


def test_repair_leaves_ambiguous_and_unknown_rows_alone() -> None:
    conn = _owner_db()
    conn.execute("INSERT INTO sermons (id, user_id) VALUES ('s-conflict', NULL)")
    conn.execute("INSERT INTO sermons (id, user_id) VALUES ('s-unknown', NULL)")
    for job_id, result in (
        ("j-a", {"data": {"sermon_id": "s-conflict"}}),
        ("j-b", {"data": {"sermon_id": "s-conflict"}}),
    ):
        conn.execute(
            "INSERT INTO background_jobs (id, type, result, user_id) VALUES (?, ?, ?, ?)",
            (job_id, "sermon_publish", json.dumps(result), "u-owner"),
        )
    conn.execute(
        "INSERT INTO background_jobs (id, type, result, user_id) VALUES (?, ?, ?, ?)",
        ("j-b2", "sermon_publish", json.dumps({"data": {"sermon_id": "s-conflict"}}), "u-other"),
    )
    conn.commit()

    summary = repair_ownerless_sermons(conn)
    assert summary["repaired"] == []
    reasons = {row["sermon_id"]: row["reason"] for row in summary["unresolved"]}
    assert reasons == {
        "s-conflict": "conflicting publish owners",
        "s-unknown": "no publish record",
    }
    assert conn.execute(
        "SELECT user_id FROM sermons WHERE id = 's-conflict'"
    ).fetchone()[0] is None
    assert conn.execute(
        "SELECT user_id FROM sermons WHERE id = 's-unknown'"
    ).fetchone()[0] is None
    conn.close()


def test_startup_migration_repairs_ownerless_row(tmp_path: Path) -> None:
    db_path = tmp_path / "startup.db"
    db = SermonDatabase(str(db_path))
    conn = _connect(str(db_path))
    conn.execute("INSERT INTO sermons (id, title, status, user_id) VALUES (?, ?, ?, ?)",
                 ("s-migrated", "Migrated", "processed", None))
    conn.execute(
        "CREATE TABLE background_jobs (id TEXT PRIMARY KEY, type TEXT, result TEXT, user_id TEXT)"
    )
    conn.execute(
        "INSERT INTO background_jobs (id, type, result, user_id) VALUES (?, ?, ?, ?)",
        (
            "j-publish",
            "sermon_publish",
            json.dumps({"data": {"sermon_id": "s-migrated"}}),
            "u-real",
        ),
    )
    conn.commit()
    conn.close()

    db.init_database()

    conn = _connect(str(db_path))
    owner = conn.execute(
        "SELECT user_id FROM sermons WHERE id = 's-migrated'"
    ).fetchone()[0]
    conn.close()
    assert owner == "u-real"
