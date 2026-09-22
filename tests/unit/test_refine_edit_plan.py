"""Re-running cut detection: rejection notes, accumulation, and re-detect."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import sermon_updater as su
from src.auto_edit import DETECTION_UNAVAILABLE, EditPlan
from ui.database import SermonDatabase, SermonRepository

CANNED_JSON = json.dumps(
    {
        "start": 245.0,
        "end": 3612.0,
        "confidence": 0.87,
        "evidence": "[04:05-04:11] In Him we live and move",
        "qa_judgment": "cut",
        "reasoning": "teaching starts after welcome",
    }
)

SEGMENTS = [
    {"start": 0.0, "end": 10.0, "text": "Welcome everyone, let us pray."},
    {"start": 245.0, "end": 255.0, "text": "In Him we live and move."},
    {"start": 3620.0, "end": 3630.0, "text": "Are there any questions before we finish?"},
]

CONFIG = {"auto_edit": {"qa_margin_seconds": 3.0, "min_sermon_seconds": 1}}


class FakeLLMManager:
    def __init__(self, response: str = CANNED_JSON):
        self.response = response
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages, operation="", sermon_id=None):
        self.calls.append(messages)
        return self.response

    def get_provider_info(self):
        return {}


@pytest.fixture
def repo(tmp_path) -> SermonRepository:
    db = SermonDatabase(db_path=str(tmp_path / "refine.db"))
    return SermonRepository(db)


@pytest.fixture
def harness(tmp_path, monkeypatch, repo) -> SimpleNamespace:
    import ui.database as db_module

    monkeypatch.setattr(db_module, "SermonRepository", lambda: repo)
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    monkeypatch.setattr(su, "_review_dir_for_refine", lambda *args, **kwargs: review_dir)
    monkeypatch.setattr(su, "read_transcript_timestamps", lambda _dir: list(SEGMENTS))
    monkeypatch.setattr(su, "read_metadata", lambda _dir: {"duration": 7200.0})
    monkeypatch.setattr(su, "_ffprobe_duration", lambda _path: 3600.0)
    rerender = Mock()
    monkeypatch.setattr(su, "_rerender_review_snippets", rerender)
    repo.save_sermon({"id": "s1", "title": "Sermon"})
    return SimpleNamespace(repo=repo, review_dir=review_dir, rerender=rerender)


def _seed(
    repo: SermonRepository,
    notes: str,
    *,
    start: float = 10.0,
    end: float = 20.0,
    evidence: str = "old evidence",
) -> int:
    return repo.save_edit_plan_revision(
        "s1",
        {
            "proposed_start": start,
            "proposed_end": end,
            "final_start": None,
            "final_end": None,
            "confidence": 0.5,
            "needs_review": True,
            "evidence": evidence,
            "qa_judgment": "cut",
            "reasoning": "old proposal",
            "detection_status": "ok",
            "status": "pending_review",
            "source_path": "audio/clip.wav",
            "notes": notes,
        },
    )


def _user_prompt(manager: FakeLLMManager) -> str:
    return manager.calls[-1][1]["content"]


def test_refine_prompt_carries_previous_plan_and_all_notes(harness, monkeypatch) -> None:
    repo = harness.repo
    _seed(repo, "First note", start=5.0, end=50.0, evidence="first evidence")
    _seed(repo, "Second note", start=10.0, end=60.0, evidence="second evidence")
    manager = FakeLLMManager()
    monkeypatch.setattr(su, "llm_manager", manager)

    result = su.refine_edit_plan("s1", notes="Third note", config=CONFIG)

    assert result["success"] is True
    assert result["notes"] == "Third note"
    assert result["accumulated_notes"] == ["First note", "Second note", "Third note"]
    prompt = _user_prompt(manager)
    assert "RE-DETECTION" in prompt
    assert "start: 10.0" in prompt
    assert "end: 60.0" in prompt
    assert "second evidence" in prompt
    for note in ("First note", "Second note", "Third note"):
        assert note in prompt
    assert prompt.index("First note") < prompt.index("Second note") < prompt.index("Third note")


def test_refine_creates_new_revision_and_supersedes_old(harness, monkeypatch) -> None:
    repo = harness.repo
    _seed(repo, "First note", start=5.0, end=50.0)
    _seed(repo, "Second note", start=10.0, end=60.0)
    monkeypatch.setattr(su, "llm_manager", FakeLLMManager())

    su.refine_edit_plan("s1", notes="Third note", config=CONFIG)

    by_rev = {row["revision"]: row for row in repo.get_edit_plan_history("s1")}
    assert sorted(by_rev) == [1, 2, 3]
    assert by_rev[1]["status"] == "superseded"
    assert by_rev[2]["status"] == "superseded"
    assert by_rev[3]["status"] == "pending_review"
    assert by_rev[3]["notes"] == "Third note"
    assert by_rev[3]["proposed_start"] == 245.0
    assert by_rev[3]["proposed_end"] == 3612.0
    assert repo.get_current_edit_plan("s1")["revision"] == 3


def test_notes_accumulate_across_rounds_and_remain_in_history(harness, monkeypatch) -> None:
    repo = harness.repo
    manager = FakeLLMManager()
    monkeypatch.setattr(su, "llm_manager", manager)

    first = su.refine_edit_plan("s1", notes="Keep only the second class", config=CONFIG)
    assert first["accumulated_notes"] == ["Keep only the second class"]

    second = su.refine_edit_plan("s1", notes="Trim the announcements", config=CONFIG)
    assert second["accumulated_notes"] == [
        "Keep only the second class",
        "Trim the announcements",
    ]
    prompt = _user_prompt(manager)
    assert prompt.index("Keep only the second class") < prompt.index("Trim the announcements")

    notes_by_rev = {row["revision"]: row["notes"] for row in repo.get_edit_plan_history("s1")}
    assert notes_by_rev == {1: "Keep only the second class", 2: "Trim the announcements"}


def test_re_detect_starts_clean_and_keeps_history(harness, monkeypatch) -> None:
    repo = harness.repo
    _seed(repo, "Keep only the second class", start=10.0, end=60.0, evidence="old evidence")
    manager = FakeLLMManager()
    monkeypatch.setattr(su, "llm_manager", manager)

    result = su.refine_edit_plan("s1", notes="", config=CONFIG, re_detect=True)

    assert result["success"] is True
    assert result["re_detect"] is True
    assert result["accumulated_notes"] == []
    assert result["notes"] == ""
    prompt = _user_prompt(manager)
    assert "RE-DETECTION" not in prompt
    assert "Keep only the second class" not in prompt
    assert "old evidence" not in prompt

    by_rev = {row["revision"]: row for row in repo.get_edit_plan_history("s1")}
    assert by_rev[1]["status"] == "superseded"
    assert by_rev[1]["notes"] == "Keep only the second class"
    assert by_rev[2]["status"] == "pending_review"
    assert by_rev[2]["notes"] == ""


def test_failed_detection_is_unavailable_not_a_whole_video_plan(harness, monkeypatch) -> None:
    failed = EditPlan(
        start=0.0,
        end=0.0,
        confidence=0.0,
        needs_review=True,
        evidence="Cut detection failed: no parsable JSON",
        reasoning="model returned prose",
        detection_status=DETECTION_UNAVAILABLE,
    )
    monkeypatch.setattr(su, "detect_cut_points", Mock(return_value=failed))

    result = su.refine_edit_plan("s1", notes="note", config=CONFIG)

    assert result["success"] is False
    assert result["detection_status"] == DETECTION_UNAVAILABLE
    assert "re-run detection" in result["error"]
    current = harness.repo.get_current_edit_plan("s1")
    assert current["detection_status"] == DETECTION_UNAVAILABLE
    harness.rerender.assert_called_once()
    assert harness.rerender.call_args.args[1].detection_status == DETECTION_UNAVAILABLE


def test_review_dir_missing_reports_error(harness, monkeypatch) -> None:
    monkeypatch.setattr(su, "_review_dir_for_refine", lambda *args, **kwargs: None)
    result = su.refine_edit_plan("s1", notes="note", config=CONFIG)
    assert result["success"] is False
    assert "Sermon directory not found" in result["error"]


def test_engine_status_notes_are_not_rejection_notes() -> None:
    history = [
        {"revision": 1, "notes": "Detected cut points (mode: interactive)"},
        {"revision": 2, "notes": "Keep only the second class"},
        {"revision": 3, "notes": "Detected cut points (mode: refine)"},
        {"revision": 4, "notes": "Keep only the second class"},
    ]
    assert su._accumulated_rejection_notes(history) == ["Keep only the second class"]


def test_rerender_replaces_stale_snippets_from_retained_media(tmp_path, monkeypatch) -> None:
    review = tmp_path / "review"
    snippets = review / "snippets"
    snippets.mkdir(parents=True)
    (snippets / "start.mp4").write_bytes(b"old")
    keeper = tmp_path / "keeper.mp4"
    keeper.write_bytes(b"video")
    plan = EditPlan(start=1.0, end=2.0, confidence=0.9, evidence="e", detection_status="ok")

    called: dict[str, object] = {}

    def fake_render(source, plan_, out_dir, logo_path=None, fade_out_tail_seconds=2.0):
        called["source"] = Path(source)
        called["fade"] = fade_out_tail_seconds
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "start.mp4").write_bytes(b"new")
        return [out_dir / "start.mp4"]

    monkeypatch.setattr("src.review_media.render_bounded_snippets", fake_render)
    meta = {
        "is_video": True,
        "keeper_file": str(keeper),
        "auto_edit": {"fade_out_tail_seconds": 1.5},
    }

    su._rerender_review_snippets(review, plan, meta)

    assert called["source"] == keeper
    assert called["fade"] == 1.5
    assert (snippets / "start.mp4").read_bytes() == b"new"


def test_rerender_clears_stale_snippets_when_unavailable(tmp_path, monkeypatch) -> None:
    review = tmp_path / "review"
    snippets = review / "snippets"
    snippets.mkdir(parents=True)
    (snippets / "start.mp4").write_bytes(b"old")
    render = Mock()
    monkeypatch.setattr("src.review_media.render_bounded_snippets", render)

    su._rerender_review_snippets(
        review,
        EditPlan(detection_status=DETECTION_UNAVAILABLE),
        {"is_video": True, "keeper_file": "keeper.mp4"},
    )

    assert not snippets.exists()
    render.assert_not_called()
