from __future__ import annotations

import pytest

from src.auto_edit import EditPlan, normalize_remove_segments, validate_plan


def _plan(segments: list[dict[str, float]] | None = None) -> EditPlan:
    return EditPlan(start=10.0, end=100.0, remove_segments=segments or [])


def test_empty_remove_segments_keeps_existing_plan_behavior() -> None:
    plan = _plan()

    assert validate_plan(plan, min_sermon_seconds=0.0) == []
    assert plan.remove_segments == []


def test_touching_ranges_are_sorted_and_merged() -> None:
    normalized, problems = normalize_remove_segments(
        [
            {"start_sec": 50.0, "end_sec": 60.0},
            {"start_sec": 20.0, "end_sec": 30.0},
            {"start_sec": 30.0, "end_sec": 40.0},
        ],
        start=10.0,
        end=100.0,
    )

    assert problems == []
    assert normalized == [
        {"start_sec": 20.0, "end_sec": 40.0},
        {"start_sec": 50.0, "end_sec": 60.0},
    ]

    plan = _plan(
        [
            {"start_sec": 50.0, "end_sec": 60.0},
            {"start_sec": 20.0, "end_sec": 30.0},
            {"start_sec": 30.0, "end_sec": 40.0},
        ]
    )
    assert validate_plan(plan, min_sermon_seconds=0.0) == []
    assert plan.remove_segments == normalized


@pytest.mark.parametrize(
    ("segments", "message"),
    [
        ([{"start_sec": 20.0, "end_sec": 19.0}], "end must be greater"),
        ([{"start_sec": 20.0, "end_sec": 20.2}], "at least 0.25"),
        ([{"start_sec": 5.0, "end_sec": 20.0}], "inside the keep window"),
        ([{"start_sec": 80.0, "end_sec": 100.0}], "inside the keep window"),
        ([{"start_sec": 10.0, "end_sec": 20.0}], "inside the keep window"),
        ([{"start_sec": 20.0, "end_sec": 100.0}], "inside the keep window"),
        (
            [
                {"start_sec": 20.0, "end_sec": 40.0},
                {"start_sec": 30.0, "end_sec": 50.0},
            ],
            "overlap",
        ),
    ],
)
def test_invalid_remove_segments_are_rejected(
    segments: list[dict[str, float]], message: str
) -> None:
    _, problems = normalize_remove_segments(segments, start=10.0, end=100.0)

    assert any(message in problem for problem in problems)
    plan = _plan(segments)
    assert any(message in problem for problem in validate_plan(plan, min_sermon_seconds=0.0))
    assert plan.remove_segments == segments


def test_minimum_kept_duration_accounts_for_removals() -> None:
    plan = _plan([{"start_sec": 20.0, "end_sec": 40.0}])

    problems = validate_plan(plan, min_sermon_seconds=71.0)

    assert any("kept duration" in problem for problem in problems)
