from __future__ import annotations

import json
import sqlite3

from server.api.accounts import get_db_path

TRANSCRIPT = "Sample teaching transcript used only for fixture generation."


def _seed_transcript(sermon_id: str, text: str = TRANSCRIPT) -> None:
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO sermon_content (sermon_id, transcript_text) VALUES (?, ?)"
        " ON CONFLICT(sermon_id) DO UPDATE SET transcript_text = excluded.transcript_text",
        (sermon_id, text),
    )
    conn.commit()
    conn.close()


def _stub_runtime(monkeypatch):
    import sermon_updater

    monkeypatch.setattr(sermon_updater, "refresh_runtime_config", lambda config=None: {})
    return sermon_updater


def test_generate_requires_auth_ownership_and_a_transcript(client, scoped_setup):
    s = scoped_setup
    body = {"field": "title"}
    assert client.post("/api/sermons/s-a/metadata/generate", json=body).status_code == 401
    assert (
        client.post(
            "/api/sermons/s-a/metadata/generate", json=body, headers=s["b"]["headers"]
        ).status_code
        == 404
    )
    missing = client.post(
        "/api/sermons/s-a/metadata/generate", json=body, headers=s["a"]["headers"]
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "no_transcript"
    assert (
        client.post(
            "/api/sermons/s-a/metadata/generate",
            json={"field": "speaker"},
            headers=s["a"]["headers"],
        ).status_code
        == 422
    )


def test_generate_title_persists_and_leaves_other_fields_alone(
    client, scoped_setup, monkeypatch
):
    s = scoped_setup
    _seed_transcript("s-a")
    updater = _stub_runtime(monkeypatch)
    monkeypatch.setattr(updater, "generate_title", lambda **kwargs: "Generated Title")
    monkeypatch.setattr(
        updater, "generate_validated_summary", lambda *args, **kwargs: ("unused", {})
    )
    monkeypatch.setattr(updater, "generate_hashtags", lambda text: "unused")

    r = client.post(
        "/api/sermons/s-a/metadata/generate",
        json={"field": "title"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"field": "title", "value": "Generated Title", "needs_review": False}

    detail = client.get("/api/sermons/s-a", headers=s["a"]["headers"]).json()
    assert detail["title"] == "Generated Title"
    assert detail["description"] is None
    assert detail["hashtags"] is None


def test_generate_description_clears_the_review_flag(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _seed_transcript("s-a")
    conn = sqlite3.connect(get_db_path())
    conn.execute("UPDATE sermons SET description_needs_review = 1 WHERE id = 's-a'")
    conn.commit()
    conn.close()
    updater = _stub_runtime(monkeypatch)
    monkeypatch.setattr(
        updater,
        "generate_validated_summary",
        lambda *args, **kwargs: (
            "A generated description.",
            {"description_needs_review": False},
        ),
    )

    r = client.post(
        "/api/sermons/s-a/metadata/generate",
        json={"field": "description"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "A generated description."
    assert r.json()["needs_review"] is False

    detail = client.get("/api/sermons/s-a", headers=s["a"]["headers"]).json()
    assert detail["description"] == "A generated description."
    assert detail["description_needs_review"] is False


def test_generate_hashtags_persists_to_content(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _seed_transcript("s-a")
    updater = _stub_runtime(monkeypatch)
    monkeypatch.setattr(updater, "generate_hashtags", lambda text: "#faith #hope")

    r = client.post(
        "/api/sermons/s-a/metadata/generate",
        json={"field": "hashtags"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "#faith #hope"

    detail = client.get("/api/sermons/s-a", headers=s["a"]["headers"]).json()
    assert detail["hashtags"] == "#faith #hope"


def test_generate_reads_the_edit_transcript_not_the_full_source(
    client, scoped_setup, monkeypatch, tmp_path
):
    s = scoped_setup
    _seed_transcript("s-a", "opening REMOVED-SENTINEL closing")
    timestamps = tmp_path / "transcript_timestamps.json"
    timestamps.write_text(
        json.dumps(
            [
                {"start": 11.0, "end": 15.0, "text": "opening"},
                {"start": 21.0, "end": 29.0, "text": "REMOVED-SENTINEL"},
                {"start": 31.0, "end": 35.0, "text": "closing"},
            ]
        ),
        encoding="utf-8",
    )
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT OR REPLACE INTO sermon_files (sermon_id, file_type, file_path)"
        " VALUES ('s-a', 'transcript_timestamps', ?)",
        (str(timestamps),),
    )
    conn.execute(
        "INSERT INTO edit_plans"
        " (sermon_id, revision, proposed_start, proposed_end, remove_segments, status)"
        " VALUES ('s-a', 1, 10.0, 40.0, ?, 'pending_review')",
        (json.dumps([{"start_sec": 20.0, "end_sec": 30.0}]),),
    )
    conn.commit()
    conn.close()

    updater = _stub_runtime(monkeypatch)
    seen: dict = {}

    def _generate_title(**kwargs):
        seen.update(kwargs)
        return "Generated Title"

    monkeypatch.setattr(updater, "generate_title", _generate_title)

    r = client.post(
        "/api/sermons/s-a/metadata/generate",
        json={"field": "title"},
        headers=s["a"]["headers"],
    )

    assert r.status_code == 200, r.text
    assert "REMOVED-SENTINEL" not in seen["transcript"]
    assert seen["transcript"] == "opening closing"


def test_generate_reports_a_timeout(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _seed_transcript("s-a")
    updater = _stub_runtime(monkeypatch)
    from src.llm_manager import LLMTimeoutError

    def _timeout(**kwargs):
        raise LLMTimeoutError("metadata-title timed out after 120s", 120)

    monkeypatch.setattr(updater, "generate_title", _timeout)

    r = client.post(
        "/api/sermons/s-a/metadata/generate",
        json={"field": "title"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 504
    assert r.json()["detail"]["code"] == "generation_timeout"

    detail = client.get("/api/sermons/s-a", headers=s["a"]["headers"]).json()
    assert detail["title"] == "Owned A"


def test_apply_carries_the_generate_metadata_choice(client, scoped_setup, monkeypatch):
    s = scoped_setup
    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setenv("DATABASE_URL", get_db_path())
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)
    monkeypatch.setattr(
        "server.api.routers.writes._require_sermonaudio_connection", lambda user_id: None
    )

    r = client.post(
        "/api/sermons/s-a/plan/apply",
        json={
            "start": 10.0,
            "end": 20.0,
            "render_only": False,
            "generate_metadata": True,
        },
        headers=s["a"]["headers"],
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT parameters FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert json.loads(row[0])["generate_metadata"] is True
