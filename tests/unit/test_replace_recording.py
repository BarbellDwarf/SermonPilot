from __future__ import annotations

import json
import sqlite3

from server.api.accounts import get_db_path

TINY_MP4 = b"\x00\x00\x00\x18ftypmp42" + bytes(1024)


def _seed_published(
    sermon_id: str,
    *,
    remote_id: str | None = "11226183043643",
    description_needs_review: bool = False,
) -> None:
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE sermons SET event_type = ?, series_title = ?, bible_text = ?,"
        " subtitle = ?, description = ?, description_needs_review = ?"
        " WHERE id = ?",
        (
            "Midweek Service",
            "All Things Prayer",
            "Luke 11:1",
            "A teaching on prayer",
            "The existing description.",
            int(description_needs_review),
            sermon_id,
        ),
    )
    if remote_id is not None:
        conn.execute(
            "INSERT OR REPLACE INTO upload_info"
            " (sermon_id, sermonaudio_id, upload_status)"
            " VALUES (?, ?, 'completed')",
            (sermon_id, remote_id),
        )
    conn.commit()
    conn.close()


def _replace(client, headers, sermon_id="s-a", content=TINY_MP4):
    return client.post(
        f"/api/sermons/{sermon_id}/recording",
        files={"file": ("replacement.mp4", content, "video/mp4")},
        headers=headers,
    )


def test_replace_queues_reprocessing_onto_the_same_entry(
    client, scoped_setup, tmp_path, monkeypatch
):
    from server.api.routers import writes

    s = scoped_setup
    ingest = tmp_path / "raw_ingest"
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(ingest))
    monkeypatch.setattr(writes, "_require_sermonaudio_connection", lambda _uid: None)
    _seed_published("s-a", description_needs_review=True)

    response = _replace(client, s["a"]["headers"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == "s-a"
    assert body["status"] == "queued"
    stored = list((ingest / s["a"]["id"]).iterdir())
    assert len(stored) == 1
    assert stored[0].stat().st_size == len(TINY_MP4)

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT parameters FROM background_jobs WHERE id = ?", (body["job_id"],)
    ).fetchone()
    conn.close()
    params = json.loads(row[0])
    form = params["form_data"]
    assert params["replace_recording"] is True
    assert params["remote_sermon_id"] == "11226183043643"
    assert params["sermon_id"] == "s-a"
    assert params["uploaded_file_path"] == str(stored[0])
    assert form["title"] == "Owned A"
    assert form["description"] == "The existing description."
    assert form["description_needs_review"] is True
    assert form["skip_ai_generation"] is True
    assert form["publish"] is True
    assert form["auto_edit_enabled"] is True
    assert form["auto_edit_mode"] == "auto"


def test_replace_refuses_an_unpublished_sermon(client, scoped_setup, tmp_path, monkeypatch):
    from server.api.routers import writes

    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw_ingest"))
    monkeypatch.setattr(writes, "_require_sermonaudio_connection", lambda _uid: None)
    _seed_published("s-a", remote_id=None)

    response = _replace(client, s["a"]["headers"])

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "not_published"


def test_replace_is_hidden_from_another_user(client, scoped_setup, tmp_path, monkeypatch):
    from server.api.routers import writes

    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw_ingest"))
    monkeypatch.setattr(writes, "_require_sermonaudio_connection", lambda _uid: None)
    _seed_published("s-a")

    assert _replace(client, s["b"]["headers"]).status_code == 404


def test_replacement_uploads_the_full_recording_when_the_auto_edit_gate_is_unsure(
    tmp_path, monkeypatch
):
    """A replacement must never stall on an interactive review pause."""
    from unittest.mock import Mock

    import sermon_updater as su
    from src.auto_edit import EditPlan

    monkeypatch.setenv("DATABASE_URL", str(tmp_path / "replacement.db"))
    monkeypatch.setattr("ui.database._db", None)
    video = tmp_path / "replacement.mp4"
    video.write_bytes(TINY_MP4)

    cfg = {
        "output_directory": str(tmp_path / "output"),
        "auto_edit": {"enabled": True, "min_sermon_seconds": 1},
    }
    monkeypatch.setattr(
        su,
        "transcribe_segments",
        Mock(return_value=[{"start": 0.0, "end": 40.0, "text": "teaching"}]),
    )
    monkeypatch.setattr(
        su,
        "detect_cut_points",
        Mock(
            return_value=EditPlan(
                start=0.0,
                end=40.0,
                confidence=0.1,
                needs_review=True,
                evidence="uncertain",
            )
        ),
    )
    apply_edit = Mock()
    monkeypatch.setattr(su, "apply_edit", apply_edit)
    create = Mock(return_value="new")
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    upload = Mock(return_value=True)
    monkeypatch.setattr(su, "upload_media_file", upload)
    monkeypatch.setattr(su, "set_sermon_published", Mock(return_value=True))

    result = su.process_new_sermon(
        str(video),
        title="Apostolic Teaching on Prayer (1)",
        description="Existing description.",
        hashtags="#existing",
        speaker_name="Mark Hogan",
        recorded_date="2026-10-28",
        event_type="Midweek Service",
        series_title="All Things Prayer",
        skip_ai_generation=True,
        skip_audio=True,
        auto_edit_mode="auto",
        publish=True,
        replace_recording=True,
        remote_sermon_id="11226183043643",
        existing_sermon_id="11226183043643",
        config=cfg,
    )

    assert result["success"] is True, result.get("error")
    assert result["edit_plan_status"] != "pending_review"
    create.assert_not_called()
    apply_edit.assert_not_called()
    upload.assert_called_once()
    assert upload.call_args.args[0] == "11226183043643"
    assert upload.call_args.args[2] == "original-video"
