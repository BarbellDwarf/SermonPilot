from __future__ import annotations

from datetime import datetime

import ui.job_labels as jl
from ui.job_labels import (
    LABEL_MAX_LENGTH,
    UNTITLED_SERMON,
    build_job_labels,
    build_job_name,
    labels_from_job,
    truncate_label,
)
from ui.job_queue import Job, JobStatus, JobType

SERMON_ID = "draft_sample_speaker_20260101_sample_sermon_0123abcd"
TITLE = "Sample Sermon"
SPEAKER = "Sample Speaker"
DATE = "2026-01-01"


def test_every_job_type_gets_a_name_without_the_id() -> None:
    for job_type in JobType:
        name, description = build_job_labels(
            job_type, title=TITLE, speaker=SPEAKER, recorded_date=DATE
        )
        assert TITLE in name, job_type
        assert SERMON_ID not in name, job_type
        assert name == name.strip()
        assert description, job_type
        assert SERMON_ID not in description, job_type
        assert description != SERMON_ID


def test_name_carries_title_and_speaker_for_a_single_sermon() -> None:
    name, _ = build_job_labels(JobType.AUTO_EDIT_APPLY, title=TITLE, speaker=SPEAKER)
    assert name == f"Apply edit · {TITLE} · {SPEAKER}"


def test_missing_title_falls_back_to_untitled_sermon() -> None:
    name, description = build_job_labels(JobType.SERMON_PROCESSING, title=None)
    assert UNTITLED_SERMON in name
    assert UNTITLED_SERMON in description


def test_blank_speaker_is_omitted() -> None:
    name, _ = build_job_labels(JobType.AUTO_EDIT, title=TITLE, speaker="   ")
    assert name == f"Auto-edit · {TITLE}"


def test_long_title_truncates_with_ellipsis_within_limit() -> None:
    long_title = "A" * 120
    name = build_job_name(JobType.SERMON_PUBLISH, title=long_title, speaker=SPEAKER)
    assert len(name) <= LABEL_MAX_LENGTH
    assert name.endswith("…")


def test_truncate_label_collapses_whitespace() -> None:
    assert truncate_label("  a   b  ") == "a b"
    assert truncate_label("x" * 200) == "x" * (LABEL_MAX_LENGTH - 1) + "…"


def test_description_is_readable_prose_not_a_restatement_of_the_id() -> None:
    _, description = build_job_labels(
        JobType.AUTO_EDIT_APPLY, title=TITLE, speaker=SPEAKER, recorded_date=DATE
    )
    assert description == f'Rendering the approved cut for "{TITLE}" ({SPEAKER}, {DATE}).'


def test_batch_variants_use_count_and_title() -> None:
    name, description = build_job_labels(
        JobType.SERMON_IMPORT, count=3
    )
    assert name == "Import · 3 sermons"
    assert "3 missing sermons" in description

    named, _ = build_job_labels(
        JobType.BATCH_PROCESSING, title=TITLE, speaker=SPEAKER, count=12
    )
    assert TITLE in named
    assert "(+11 more)" in named


def test_labels_from_job_rebuilds_processing_from_form_data() -> None:
    job = Job(
        id="job-1",
        type=JobType.SERMON_PROCESSING,
        title="ignored",
        description="ignored",
        status=JobStatus.COMPLETED,
        progress=100.0,
        created_at=datetime.now(),
        parameters={
            "form_data": {
                "title": TITLE,
                "speaker_name": SPEAKER,
                "recorded_date": DATE,
                "auto_edit_enabled": False,
            }
        },
    )
    name, description = labels_from_job(job)
    assert TITLE in name
    assert SPEAKER in name
    assert "job-1" not in name
    assert SERMON_ID not in name
    assert TITLE in description


def test_labels_from_job_infers_apply_variant_from_params() -> None:
    job = Job(
        id="job-2",
        type=JobType.AUTO_EDIT_APPLY,
        title="ignored",
        description="ignored",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters={"sermon_id": "s-1", "render_only": False},
    )
    _, description = labels_from_job(job)
    assert "uploading it to SermonAudio" in description


def test_sermon_fields_for_reads_the_repository(monkeypatch) -> None:
    class _Repo:
        def get_sermon(self, sermon_id: str) -> dict[str, str]:
            assert sermon_id == "s-1"
            return {"title": TITLE, "speaker": SPEAKER, "recorded_date": DATE}

    monkeypatch.setattr("ui.database.SermonRepository", lambda: _Repo())
    assert jl.sermon_fields_for(["s-1"]) == {
        "title": TITLE,
        "speaker": SPEAKER,
        "recorded_date": DATE,
    }
    assert jl.sermon_fields_for([]) == {}


def test_sermon_fields_for_uses_the_supplied_repository() -> None:
    seen: list[str] = []

    class _Repo:
        def get_sermon(self, sermon_id: str) -> dict[str, str]:
            seen.append(sermon_id)
            return {"title": TITLE, "speaker": SPEAKER, "recorded_date": DATE}

    assert jl.sermon_fields_for(["s-9"], repo=_Repo()) == {
        "title": TITLE,
        "speaker": SPEAKER,
        "recorded_date": DATE,
    }
    assert seen == ["s-9"]
