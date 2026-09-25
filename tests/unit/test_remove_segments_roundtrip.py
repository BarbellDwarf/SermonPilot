from __future__ import annotations

import json
from pathlib import Path

from sermon_updater import _load_edit_plan_from_file
from ui.auto_edit_apply import _write_edit_plan_file, build_apply_job_params
from ui.database import SermonDatabase, SermonRepository


def test_edit_plan_file_round_trips_remove_segments(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(
            {
                "start": 10.0,
                "end": 100.0,
                "remove_segments": [
                    {"start_sec": 30.0, "end_sec": 40.0},
                    {"start_sec": 60.0, "end_sec": 70.0},
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = _load_edit_plan_from_file(path)

    assert plan.remove_segments == [
        {"start_sec": 30.0, "end_sec": 40.0},
        {"start_sec": 60.0, "end_sec": 70.0},
    ]


def test_edit_plan_revision_round_trips_remove_segments(tmp_path: Path) -> None:
    db = SermonDatabase(db_path=str(tmp_path / "plans.db"))
    repo = SermonRepository(db)
    repo.save_sermon({"id": "s-1", "title": "Synthetic plan"})
    plan_id = repo.save_edit_plan_revision(
        "s-1",
        {
            "proposed_start": 10.0,
            "proposed_end": 100.0,
            "remove_segments": [
                {"start_sec": 30.0, "end_sec": 40.0},
                {"start_sec": 60.0, "end_sec": 70.0},
            ],
            "status": "pending_review",
        },
    )

    row = repo.get_current_edit_plan("s-1")

    assert row is not None
    assert row["id"] == plan_id
    assert json.loads(row["remove_segments"]) == [
        {"start_sec": 30.0, "end_sec": 40.0},
        {"start_sec": 60.0, "end_sec": 70.0},
    ]


def test_legacy_edit_plan_file_defaults_to_no_removals(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"start": 10.0, "end": 100.0}), encoding="utf-8")



def test_apply_job_file_and_queue_params_carry_remove_segments() -> None:
    segments = [{"start_sec": 30.0, "end_sec": 40.0}]
    plan_path = _write_edit_plan_file(7, 10.0, 100.0, 0.2, segments)
    assert plan_path is not None
    try:
        assert _load_edit_plan_from_file(plan_path).remove_segments == segments
    finally:
        Path(plan_path).unlink(missing_ok=True)

    params = build_apply_job_params(
        "s-1", 7, 2, 10.0, 100.0, 0.2, True, False, {}, remove_segments=segments
    )
    assert params["remove_segments"] == segments
