from __future__ import annotations

import json
import sqlite3

from server.api.accounts import get_db_path


def _seed_plan(sermon_id: str) -> None:
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO edit_plans (sermon_id, revision, proposed_start, proposed_end, status) "
        "VALUES (?, 1, 10.0, 100.0, 'pending_review')",
        (sermon_id,),
    )
    conn.commit()
    conn.close()


def _job_parameters(job_id: str) -> dict:
    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT parameters FROM background_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    return json.loads(row[0])


def test_apply_records_normalized_remove_segments_on_plan_revision(
    client, scoped_setup, monkeypatch
) -> None:
    s = scoped_setup
    created = client.post(
        "/api/sermons",
        json={"title": "Synthetic cuts", "speaker": "A", "recorded_date": "2026-09-10"},
        headers=s["a"]["headers"],
    ).json()
    sermon_id = created["id"]
    _seed_plan(sermon_id)

    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)

    response = client.post(
        f"/api/sermons/{sermon_id}/plan/apply",
        json={
            "start": 10.0,
            "end": 100.0,
            "remove_segments": [
                {"start_sec": 60.0, "end_sec": 70.0},
                {"start_sec": 30.0, "end_sec": 40.0},
                {"start_sec": 40.0, "end_sec": 50.0},
            ],
            "render_only": True,
        },
        headers=s["a"]["headers"],
    )

    assert response.status_code == 202, response.text
    params = _job_parameters(response.json()["job_id"])
    assert params["remove_segments"] == [
        {"start_sec": 30.0, "end_sec": 50.0},
        {"start_sec": 60.0, "end_sec": 70.0},
    ]

    plan_response = client.get(
        f"/api/sermons/{sermon_id}/plan", headers=s["a"]["headers"]
    )
    assert plan_response.status_code == 200
    plan = plan_response.json()["plan"]
    assert plan["revision"] == 2
    assert plan["remove_segments"] == params["remove_segments"]


def test_apply_rejects_overlapping_remove_segments(client, scoped_setup, monkeypatch) -> None:
    s = scoped_setup
    created = client.post(
        "/api/sermons",
        json={"title": "Invalid cuts", "speaker": "A", "recorded_date": "2026-09-10"},
        headers=s["a"]["headers"],
    ).json()
    sermon_id = created["id"]
    _seed_plan(sermon_id)

    import ui.database as dbmod

    monkeypatch.setattr(dbmod, "_db", None)
    monkeypatch.setattr("ui.job_queue.JobQueue._resources_available", lambda self: False)

    response = client.post(
        f"/api/sermons/{sermon_id}/plan/apply",
        json={
            "start": 10.0,
            "end": 100.0,
            "remove_segments": [
                {"start_sec": 30.0, "end_sec": 50.0},
                {"start_sec": 40.0, "end_sec": 60.0},
            ],
        },
        headers=s["a"]["headers"],
    )

    assert response.status_code == 422
    assert "overlap" in response.text
