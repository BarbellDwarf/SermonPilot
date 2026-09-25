from __future__ import annotations

import sqlite3

from server.api.accounts import get_db_path

TITLE = "Console Talk"
SPEAKER = "Console Speaker"
DATE = "2026-09-20"


def _draft(client, headers):
    created = client.post(
        "/api/sermons",
        json={"title": TITLE, "speaker": SPEAKER, "recorded_date": DATE},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _stored_labels(job_id):
    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT title, description FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    return row


def _listed(client, headers, job_id):
    items = client.get("/api/jobs", headers=headers).json()["items"]
    return next(item for item in items if item["id"] == job_id)


def _free_worker(monkeypatch):
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)


def test_apply_job_label_names_the_sermon_and_reaches_the_console(
    client, scoped_setup, monkeypatch
):
    s = scoped_setup
    _free_worker(monkeypatch)
    sermon_id = _draft(client, s["a"]["headers"])

    r = client.post(
        f"/api/sermons/{sermon_id}/plan/apply",
        json={"start": 10.0, "end": 20.0, "render_only": True},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    title, description = _stored_labels(job_id)
    assert TITLE in title
    assert SPEAKER in title
    assert sermon_id not in title
    assert description == f'Rendering the approved cut for "{TITLE}" ({SPEAKER}, {DATE}).'

    item = _listed(client, s["a"]["headers"], job_id)
    assert item["title"] == title
    assert item["description"] == description


def test_upload_job_label_says_what_is_uploaded(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _free_worker(monkeypatch)
    sermon_id = _draft(client, s["a"]["headers"])

    r = client.post(f"/api/sermons/{sermon_id}/upload", headers=s["a"]["headers"])
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    title, description = _stored_labels(job_id)
    assert title.startswith("Upload")
    assert TITLE in title
    assert sermon_id not in title
    assert description == f'Uploading "{TITLE}" ({SPEAKER}, {DATE}) to SermonAudio.'


def test_refine_job_reads_as_prose(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _free_worker(monkeypatch)
    sermon_id = _draft(client, s["a"]["headers"])

    r = client.post(
        f"/api/sermons/{sermon_id}/plan/refine",
        json={"notes": "Keep the second class"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 202, r.text
    title, description = _stored_labels(r.json()["job_id"])
    assert TITLE in title
    assert SPEAKER in title
    assert sermon_id not in title
    assert description.startswith("Refining the proposed cut")
    assert "review notes" in description


def test_re_detect_job_reads_as_prose(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _free_worker(monkeypatch)
    sermon_id = _draft(client, s["a"]["headers"])

    r = client.post(
        f"/api/sermons/{sermon_id}/plan/re-detect", headers=s["a"]["headers"]
    )
    assert r.status_code == 202, r.text
    title, description = _stored_labels(r.json()["job_id"])
    assert TITLE in title
    assert sermon_id not in title
    assert description.startswith("Re-detecting the opening and closing cut")


def test_new_sermon_job_label_avoids_the_original_path(
    client, scoped_setup, tmp_path, monkeypatch
):
    s = scoped_setup
    monkeypatch.setenv("SERMONPILOT_RAW_INGEST", str(tmp_path))
    src = tmp_path / "raw_service.mp3"
    src.write_bytes(b"ID3" + bytes(2048))

    r = client.post(
        "/api/sermons/server-path",
        json={
            "container_path": str(src),
            "title": TITLE,
            "speaker": SPEAKER,
            "recorded_date": DATE,
            "event_type": "Sunday Service",
        },
        headers=s["a"]["headers"],
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]

    title, description = _stored_labels(job_id)
    assert title == f"Process sermon · {TITLE} · {SPEAKER}"
    assert str(src) not in title
    assert description == f'Running the processing pipeline for "{TITLE}" ({SPEAKER}, {DATE}).'
