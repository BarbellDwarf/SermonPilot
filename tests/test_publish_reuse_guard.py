"""Reuse-guard tests for the publish/retry path.

A local numeric-id row with no remote existence must never be reused as a
publish target: 404/empty remote details (or an API error) must fall through
to the normal create path. A row that really exists remotely stays reusable.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import Mock

import sermon_updater as su


def _unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def _seed_processed_row(title: str, speaker: str, date: str, row_id: str) -> None:
    from ui.database import SermonRepository

    repo = SermonRepository()
    assert repo.save_sermon({
        'id': row_id,
        'title': title,
        'speaker': speaker,
        'recorded_date': date,
        'status': 'processed',
    }) is True


def _drive_process(monkeypatch, tmp_path: Path, *, title: str, speaker: str,
                   date: str, create_id: str | None):
    audio_file = tmp_path / "sermon.mp3"
    audio_file.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(su, "config", {"output_directory": str(tmp_path / "output")})
    monkeypatch.setattr(su, "resolve_speaker_id", lambda name: None)
    create = Mock(return_value=create_id)
    upload = Mock(return_value=True)
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "upload_media_file", upload)
    result = su.process_new_sermon(
        str(audio_file),
        speaker_name=speaker,
        recorded_date=date,
        title=title,
        description="Test description",
        hashtags="#test",
        dry_run=False,
        skip_audio=True,
        skip_transcription=True,
    )
    return result, create, upload


def test_ghost_row_not_reused_when_remote_missing(tmp_path, monkeypatch) -> None:
    title, speaker, date = _unique("Ghost"), _unique("Speaker"), "2024-05-01"
    ghost_id = "99900011"
    _seed_processed_row(title, speaker, date, ghost_id)
    assert su._find_existing_processed_sermon_id(title, speaker, date) == ghost_id

    monkeypatch.setattr(su, "get_sermon_details", lambda sermon_id: {})
    result, create, upload = _drive_process(
        monkeypatch, tmp_path, title=title, speaker=speaker, date=date,
        create_id="777001",
    )

    assert result["success"] is True
    create.assert_called_once()
    upload.assert_called_once()
    assert upload.call_args.args[0] == "777001"


def test_legit_row_reused_when_remote_exists(tmp_path, monkeypatch) -> None:
    title, speaker, date = _unique("Legit"), _unique("Speaker"), "2024-05-02"
    real_id = "99900012"
    _seed_processed_row(title, speaker, date, real_id)

    monkeypatch.setattr(
        su, "get_sermon_details", lambda sermon_id: {"sermonID": real_id}
    )
    result, create, upload = _drive_process(
        monkeypatch, tmp_path, title=title, speaker=speaker, date=date,
        create_id="777002",
    )

    assert result["success"] is True
    create.assert_not_called()
    upload.assert_called_once()
    assert upload.call_args.args[0] == real_id


def test_api_error_falls_through_to_create(tmp_path, monkeypatch) -> None:
    title, speaker, date = _unique("Flaky"), _unique("Speaker"), "2024-05-03"
    ghost_id = "99900013"
    _seed_processed_row(title, speaker, date, ghost_id)

    def _boom(sermon_id: str):
        raise RuntimeError("network down")

    monkeypatch.setattr(su, "get_sermon_details", _boom)
    result, create, upload = _drive_process(
        monkeypatch, tmp_path, title=title, speaker=speaker, date=date,
        create_id="777003",
    )

    assert result["success"] is True
    create.assert_called_once()
    assert upload.call_args.args[0] == "777003"


def test_failed_publish_row_excluded_from_reuse() -> None:
    from ui.database import SermonRepository

    title, speaker, date = _unique("Failed"), _unique("Speaker"), "2024-05-04"
    failed_id = f"9{uuid.uuid4().hex[:7]}"
    repo = SermonRepository()
    assert repo.save_sermon({
        'id': failed_id,
        'title': title,
        'speaker': speaker,
        'recorded_date': date,
        'status': 'error',
        'upload_info': {
            'sermonaudio_id': failed_id,
            'upload_status': 'failed',
            'upload_message': 'Sermon created but audio upload failed',
        },
    }) is True

    assert su._find_existing_processed_sermon_id(title, speaker, date) is None


def test_processed_row_with_failed_upload_excluded_from_reuse() -> None:
    from ui.database import SermonRepository

    title, speaker, date = _unique("Stale"), _unique("Speaker"), "2024-05-05"
    stale_id = f"9{uuid.uuid4().hex[:7]}"
    repo = SermonRepository()
    assert repo.save_sermon({
        'id': stale_id,
        'title': title,
        'speaker': speaker,
        'recorded_date': date,
        'status': 'processed',
        'upload_info': {
            'sermonaudio_id': stale_id,
            'upload_status': 'failed',
            'upload_message': 'media upload failed',
        },
    }) is True

    assert su._find_existing_processed_sermon_id(title, speaker, date) is None
