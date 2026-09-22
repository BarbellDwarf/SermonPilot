from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from server.api.accounts import get_db_path
from src.sermon_identity import derive_sermon_id, source_fingerprint

TINY_MP3 = b"ID3" + bytes(2048)


def test_derive_id_is_stable_and_identity_sensitive():
    base = derive_sermon_id("Pastor A", "2026-09-20", "Grace", "local:abc")
    assert base == derive_sermon_id("pastor  a", "2026-09-20", "Grace!", "local:abc")
    assert derive_sermon_id("Pastor B", "2026-09-20", "Grace", "local:abc") != base
    assert derive_sermon_id("Pastor A", "2026-09-21", "Grace", "local:abc") != base
    assert derive_sermon_id("Pastor A", "2026-09-20", "Mercy", "local:abc") != base
    assert derive_sermon_id("Pastor A", "2026-09-20", "Grace", "local:def") != base
    assert base.startswith("draft_")
    assert all(char.isalnum() or char in "_-" for char in base)


def test_content_fingerprint_survives_restaging(tmp_path: Path):
    original = tmp_path / "sermon.mp3"
    original.write_bytes(TINY_MP3)
    restaged = tmp_path / "1712345678_sermon.mp3"
    shutil.copy2(original, restaged)
    assert source_fingerprint(original) == source_fingerprint(restaged)

    restaged.write_bytes(TINY_MP3 + b"x")
    assert source_fingerprint(original) != source_fingerprint(restaged)


def _server_path_body(src: Path, **overrides) -> dict:
    body = {
        "container_path": str(src),
        "title": "Server Talk",
        "speaker": "Speaker A",
        "recorded_date": "2026-09-14",
        "event_type": "Sunday Service",
    }
    body.update(overrides)
    return body


def _sermon_count(predicate: str, params: tuple = ()) -> int:
    conn = sqlite3.connect(get_db_path())
    try:
        return conn.execute(
            f"SELECT COUNT(*) FROM sermons WHERE {predicate}", params
        ).fetchone()[0]
    finally:
        conn.close()


def test_same_server_source_updates_one_row(client, scoped_setup, tmp_path):
    s = scoped_setup
    src = tmp_path / "talk.mp3"
    src.write_bytes(TINY_MP3)
    body = _server_path_body(src)

    first = client.post("/api/sermons/server-path", json=body, headers=s["a"]["headers"])
    second = client.post("/api/sermons/server-path", json=body, headers=s["a"]["headers"])
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    assert _sermon_count("speaker = ? AND title = ?", ("Speaker A", "Server Talk")) == 1


def test_same_uploaded_bytes_updates_one_row(client, scoped_setup, tmp_path, monkeypatch):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path / "raw"))

    def post(filename: str):
        return client.post(
            "/api/sermons/upload",
            files={"file": (filename, TINY_MP3, "audio/mpeg")},
            data={
                "title": "Uploaded Talk",
                "speaker": "Speaker A",
                "recorded_date": "2026-09-13",
                "event_type": "Sunday Service",
            },
            headers=s["a"]["headers"],
        )

    first = post("first.mp3")
    second = post("second.mp3")
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    assert _sermon_count("speaker = ? AND title = ?", ("Speaker A", "Uploaded Talk")) == 1


def test_distinct_sermons_stay_two_rows(client, scoped_setup, tmp_path):
    s = scoped_setup
    talk_a = tmp_path / "a.mp3"
    talk_b = tmp_path / "b.mp3"
    talk_a.write_bytes(b"ID3" + bytes(1000))
    talk_b.write_bytes(b"ID3" + bytes(2000))

    first = client.post(
        "/api/sermons/server-path",
        json=_server_path_body(talk_a, title="Alpha", recorded_date="2026-09-14"),
        headers=s["a"]["headers"],
    )
    second = client.post(
        "/api/sermons/server-path",
        json=_server_path_body(talk_b, title="Beta", recorded_date="2026-09-15"),
        headers=s["a"]["headers"],
    )
    assert first.json()["id"] != second.json()["id"]
    assert _sermon_count("title IN ('Alpha', 'Beta')") == 2


def test_migration_collapses_duplicates_and_is_idempotent(tmp_path: Path):
    from ui.database import SermonDatabase, SermonRepository

    media = tmp_path / "render.mp3"
    media.write_bytes(TINY_MP3)
    repo = SermonRepository(SermonDatabase(db_path=str(tmp_path / "dedupe.db")))

    repo.save_sermon({
        "id": "rich",
        "title": "Grace",
        "speaker": "Pastor A",
        "recorded_date": "2026-09-20",
        "status": "draft",
        "file_paths": {"audio": str(media)},
        "content": {"transcript_text": "a long transcript " * 20},
    })
    repo.save_sermon({
        "id": "thin_one",
        "title": "grace",
        "speaker": "pastor a",
        "recorded_date": "2026-09-20",
        "status": "draft",
    })
    repo.update_sermon_metadata("thin_one", {"notes": "keep this note"})
    repo.save_sermon({
        "id": "thin_two",
        "title": "Grace",
        "speaker": "Pastor A",
        "recorded_date": "2026-09-20",
        "status": "draft",
    })
    repo.save_edit_plan_revision("thin_one", {
        "proposed_start": 1.0,
        "proposed_end": 2.0,
        "status": "pending_review",
    })

    summary = repo.dedupe_sermons()
    assert summary["groups"] == 1
    rows = repo.get_all_sermons()
    assert len(rows) == 1
    kept = rows[0]["id"]
    assert kept == "rich"
    assert repo.get_sermon_files(kept)
    assert repo.get_edit_plan_history(kept)
    assert repo.get_sermon(kept)["notes"] == "keep this note"

    second = repo.dedupe_sermons()
    assert second == {"groups": 0, "merged": []}
    assert len(repo.get_all_sermons()) == 1


def test_fold_keeps_survivor_file_record(tmp_path: Path):
    from ui.database import SermonDatabase, SermonRepository

    staged = tmp_path / "staged.mp3"
    staged.write_bytes(TINY_MP3)
    canonical = tmp_path / "canonical.mp3"
    repo = SermonRepository(SermonDatabase(db_path=str(tmp_path / "fold.db")))
    repo.save_sermon({
        "id": "surv",
        "title": "T",
        "speaker": "S",
        "recorded_date": "2026-09-20",
        "file_paths": {"audio": str(canonical)},
    })
    repo.save_sermon({
        "id": "lose",
        "title": "T",
        "speaker": "S",
        "recorded_date": "2026-09-20",
        "file_paths": {"audio": str(staged)},
    })

    with repo.db.get_connection() as conn:
        repo._fold_sermon(conn, "surv", "lose")
        conn.commit()

    files = {row["file_type"]: row["file_path"] for row in repo.get_sermon_files("surv")}
    assert files["audio"] == str(canonical)
    assert repo.get_sermon_files("lose") == []


def test_migration_carries_processed_status(tmp_path: Path):
    from ui.database import SermonDatabase, SermonRepository

    media = tmp_path / "render.mp3"
    media.write_bytes(TINY_MP3)
    repo = SermonRepository(SermonDatabase(db_path=str(tmp_path / "status.db")))
    repo.save_sermon({
        "id": "draft_rich",
        "title": "Grace",
        "speaker": "Pastor A",
        "recorded_date": "2026-09-20",
        "status": "draft",
        "file_paths": {"audio": str(media)},
    })
    repo.save_sermon({
        "id": "published",
        "title": "Grace",
        "speaker": "Pastor A",
        "recorded_date": "2026-09-20",
        "status": "processed",
        "upload_info": {"sermonaudio_id": "999", "upload_status": "completed"},
    })

    summary = repo.dedupe_sermons()

    assert summary["groups"] == 1
    rows = repo.get_all_sermons()
    assert len(rows) == 1
    assert rows[0]["id"] == "draft_rich"
    kept = repo.get_sermon("draft_rich")
    assert kept["status"] == "processed"
    assert kept["upload_info"]["sermonaudio_id"] == "999"


def test_apply_reuses_existing_sermon_id():
    from ui.auto_edit_apply import _build_apply_kwargs

    kwargs = _build_apply_kwargs(
        {"speaker": "A", "title": "T", "recorded_date": "2026-09-20"},
        "/tmp/m.mp4",
        None,
        True,
        0.0,
        existing_sermon_id="draft_existing",
    )
    assert kwargs["existing_sermon_id"] == "draft_existing"
    assert kwargs["dry_run"] is True


def test_resolve_identity_id_prefers_existing():
    from sermon_updater import _resolve_identity_id

    assert (
        _resolve_identity_id("S", "2026-09-20", "T", "source.mp3", "draft_existing")
        == "draft_existing"
    )
    derived = _resolve_identity_id("S", "2026-09-20", "T", "source.mp3")
    assert derived == _resolve_identity_id("S", "2026-09-20", "T", "source.mp3")
