"""Plan values are validated before any job exists.

Negative starts and windows past the media duration are refused with 422, and
non-finite numbers never reach the queue. The API used to validate without the
sermon duration and without a finite check, so NaN slipped through.
"""

from __future__ import annotations

import sqlite3

from server.api.accounts import get_db_path


def _draft(client, headers, duration=3600.0):
    created = client.post(
        "/api/sermons",
        json={"title": "Plan Values", "speaker": "Speaker A", "recorded_date": "2026-10-22"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    sermon_id = created.json()["id"]
    conn = sqlite3.connect(get_db_path())
    conn.execute("UPDATE sermons SET duration = ? WHERE id = ?", (duration, sermon_id))
    conn.commit()
    conn.close()
    return sermon_id


def _job_count(sermon_id: str) -> int:
    conn = sqlite3.connect(get_db_path())
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM background_jobs WHERE parameters LIKE ?",
            (f"%{sermon_id}%",),
        ).fetchone()[0]
    finally:
        conn.close()


def test_negative_start_is_422(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    sermon_id = _draft(client, headers)
    response = client.post(
        f"/api/sermons/{sermon_id}/plan/apply",
        json={"start": -5.0, "end": 20.0, "render_only": True},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert "start is negative" in str(response.json()["detail"])
    assert _job_count(sermon_id) == 0


def test_end_past_media_duration_is_422(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    sermon_id = _draft(client, headers, duration=120.0)
    response = client.post(
        f"/api/sermons/{sermon_id}/plan/apply",
        json={"start": 10.0, "end": 500.0, "render_only": True},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert "end exceeds video duration" in str(response.json()["detail"])
    assert _job_count(sermon_id) == 0


def test_nan_plan_values_are_422_not_500(client, scoped_setup):
    headers = {**scoped_setup["a"]["headers"], "Content-Type": "application/json"}
    sermon_id = _draft(client, headers)
    for body in (
        '{"start": NaN, "end": 20.0, "render_only": true}',
        '{"start": 10.0, "end": NaN, "render_only": true}',
        '{"start": 10.0, "end": 20.0, "render_only": true,'
        ' "remove_segments": [{"start_sec": NaN, "end_sec": 15.0}]}',
    ):
        response = client.post(
            f"/api/sermons/{sermon_id}/plan/apply", content=body, headers=headers
        )
        assert response.status_code == 422, (body, response.status_code, response.text)
    assert _job_count(sermon_id) == 0


def test_validate_plan_rejects_non_finite_values_directly():
    from src.auto_edit import EditPlan, validate_plan

    for plan in (
        EditPlan(start=float("nan"), end=20.0),
        EditPlan(start=0.0, end=float("inf")),
        EditPlan(start=0.0, end=20.0, audio_offset=float("nan")),
    ):
        assert any("finite" in problem for problem in validate_plan(plan))
