"""The uploaded transcript must match the applied edit's kept spans."""

from __future__ import annotations

from src.auto_edit import EditPlan, finalize_transcript, kept_transcript_spans


def _plan(**overrides) -> EditPlan:
    values = {
        "start": 10.0,
        "end": 40.0,
        "remove_segments": [{"start_sec": 20.0, "end_sec": 30.0}],
    }
    values.update(overrides)
    return EditPlan(**values)


def test_kept_spans_wrap_removed_ranges() -> None:
    assert kept_transcript_spans(_plan()) == [(10.0, 20.0), (30.0, 40.0)]


def test_finalize_drops_removed_and_out_of_window_entries() -> None:
    segments = [
        {"start": 0.0, "end": 5.0, "text": "before"},
        {"start": 11.0, "end": 15.0, "text": "opening"},
        {"start": 21.0, "end": 29.0, "text": "removed"},
        {"start": 31.0, "end": 35.0, "text": "closing"},
        {"start": 45.0, "end": 50.0, "text": "after"},
    ]

    kept, text = finalize_transcript(segments, _plan())

    assert text == "opening closing"
    assert [segment["text"] for segment in kept] == ["opening", "closing"]
    assert kept[0]["start"] == 1.0
    assert kept[0]["end"] == 5.0
    assert kept[1]["start"] == 11.0
    assert kept[1]["end"] == 15.0


def test_finalize_clips_a_boundary_entry_once() -> None:
    segments = [{"start": 18.0, "end": 22.0, "text": "straddles the cut"}]

    kept, text = finalize_transcript(segments, _plan())

    assert text == "straddles the cut"
    assert len(kept) == 1
    assert kept[0]["start"] == 8.0
    assert kept[0]["end"] == 10.0
