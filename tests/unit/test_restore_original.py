"""Restore-original: resolve the unedited recording and repoint the sermon."""

from __future__ import annotations

import json
from pathlib import Path

from src.restore_original import _same_length, restore_original
from ui.database import SermonDatabase, SermonRepository


def _repo(tmp_path: Path) -> SermonRepository:
    db = SermonDatabase(db_path=str(tmp_path / "restore.db"))
    db.init_database()
    return SermonRepository(db)


def _seed(repo: SermonRepository, sermon_id: str, duration: float, rows: dict[str, Path]) -> None:
    with repo.db.get_connection() as conn:
        conn.execute(
            "INSERT INTO sermons (id, title, speaker, status, duration, edit_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sermon_id, "Restore test", "Mark Hogan", "draft", duration, "applied"),
        )
        for kind, path in rows.items():
            conn.execute(
                "INSERT INTO sermon_files (sermon_id, file_type, file_path, file_size) "
                "VALUES (?, ?, ?, ?)",
                (sermon_id, kind, str(path), path.stat().st_size if path.exists() else 0),
            )
        conn.commit()


def test_restore_uses_original_and_existing_preview(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    sermon_id = "draft_restore_1"
    media = tmp_path / "media"
    media.mkdir()
    original = media / "sermon - Original.mkv"
    original.write_bytes(b"ORIGINAL")
    preview = media / "sermon - Preview.mp4"
    preview.write_bytes(b"PREVIEW")
    processed = media / "sermon - Processed.mp4"
    processed.write_bytes(b"PROCESSED")
    metadata = media / "metadata.json"
    metadata.write_text(
        json.dumps({"original_file": str(original), "processed_file": str(processed)}),
        encoding="utf-8",
    )
    _seed(
        repo,
        sermon_id,
        100.0,
        {
            "metadata": metadata,
            "audio": processed,
            "processed": processed,
            "processed_audio": processed,
            "original_video": original,
            "preview": preview,
        },
    )

    result = restore_original(sermon_id, repo)

    assert result["original_path"] == str(original)
    assert result["preview_path"] == str(preview)
    assert result["duration"] == 100.0
    data = json.loads(metadata.read_text(encoding="utf-8"))
    assert data["original_file"] == str(original)
    assert "processed_file" not in data
    assert data["preview_file"] == str(preview)

    rows = {row["file_type"]: row["file_path"] for row in repo.get_sermon_files(sermon_id)}
    assert rows["audio"] == str(preview)
    assert rows["preview"] == str(preview)
    assert "processed" not in rows
    assert "processed_audio" not in rows

    plan = repo.get_current_edit_plan(sermon_id)
    assert plan is not None
    assert plan["status"] == "draft"
    assert plan["final_start"] == 0.0
    assert plan["final_end"] == 100.0
    assert plan["source_path"] == str(original)
    assert repo.get_sermon_edit_status(sermon_id) == "draft"


def test_same_length_treats_unreadable_duration_as_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    import sermon_updater

    original = tmp_path / "sermon - Original.mkv"
    original.write_bytes(b"ORIGINAL")
    preview = tmp_path / "sermon - Preview.mp4"
    preview.write_bytes(b"PREVIEW")

    durations = iter([0.0, 1159.967])
    monkeypatch.setattr(sermon_updater, "_ffprobe_duration", lambda _path: next(durations))
    assert _same_length(original, preview) is True

    durations = iter([1159.0, 1160.0])
    monkeypatch.setattr(sermon_updater, "_ffprobe_duration", lambda _path: next(durations))
    assert _same_length(original, preview) is True

    durations = iter([100.0, 200.0])
    monkeypatch.setattr(sermon_updater, "_ffprobe_duration", lambda _path: next(durations))
    assert _same_length(original, preview) is False


def test_restore_finds_sibling_original_when_metadata_is_stale(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    sermon_id = "processed_restore_1"
    media = tmp_path / "published"
    media.mkdir()
    original = media / "sermon - Original.mkv"
    original.write_bytes(b"ORIGINAL")
    processed = media / "sermon - Processed.mkv"
    processed.write_bytes(b"PROCESSED")
    metadata = media / "metadata.json"
    metadata.write_text(
        json.dumps({"original_file": str(tmp_path / "gone" / "sermon - Original.mkv")}),
        encoding="utf-8",
    )
    _seed(
        repo,
        sermon_id,
        50.0,
        {"metadata": metadata, "audio": processed},
    )

    result = restore_original(sermon_id, repo)

    assert result["original_path"] == str(original)
    assert result["preview_path"] is None
    data = json.loads(metadata.read_text(encoding="utf-8"))
    assert data["original_file"] == str(original)
    assert "preview_file" not in data
    rows = {row["file_type"]: row["file_path"] for row in repo.get_sermon_files(sermon_id)}
    assert rows["audio"] == str(original)
    assert "preview" not in rows
