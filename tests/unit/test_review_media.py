"""Retention, snippet caps, and cleanup for interactive auto-edit review media."""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.review_media import (
    MARKER_FILENAME,
    finalize_review_media,
    render_bounded_snippets,
    resolve_review_media_root,
    retention_summary,
    snippet_windows,
    sweep_abandoned_reviews,
    write_review_marker,
)


def _review_dir(root: Path, name: str = "review-1") -> Path:
    review_dir = root / "speaker" / "series" / name
    review_dir.mkdir(parents=True, exist_ok=True)
    write_review_marker(review_dir, name)
    return review_dir


def _seed_review(review_dir: Path, staged: Path | None = None) -> None:
    (review_dir / "Sermon - Original.mp4").write_bytes(b"original")
    (review_dir / "Sermon - Processed.mp4").write_bytes(b"processed")
    snippets = review_dir / "snippets"
    snippets.mkdir(exist_ok=True)
    for name in ("snippet_start.mp4", "snippet_end.mp4", "snippet_ending.mp4"):
        (snippets / name).write_bytes(b"clip")
    metadata = {"staged_file": str(staged) if staged else None}
    (review_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_resolve_review_media_root_honours_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(tmp_path / "explicit"))
    assert resolve_review_media_root({"output_directory": str(tmp_path / "out")}) == (
        tmp_path / "explicit"
    )


def test_resolve_review_media_root_falls_back_from_cloud_output(tmp_path, monkeypatch):
    monkeypatch.delenv("SERMONPILOT_REVIEW_MEDIA_DIR", raising=False)
    monkeypatch.setenv("SERMONPILOT_CLOUD_OUTPUT_DIR", str(tmp_path / "cloud_output"))
    root = resolve_review_media_root({"output_directory": str(tmp_path / "cloud_output" / "job")})
    assert root == resolve_review_media_root({"output_directory": "processed_sermons"})
    assert root.name == "review_media"


def test_snippet_windows_cover_the_cut():
    windows = snippet_windows(30.0, 600.0)
    assert windows["snippet_start"] == (20.0, 40.0)
    assert windows["snippet_end"] == (590.0, 610.0)
    assert windows["snippet_ending"] == (570.0, 600.0)


def test_snippet_windows_stay_inside_source_duration():
    duration = 700.0
    for window in snippet_windows(30.0, 600.0).values():
        assert 0.0 <= window[0]
        assert window[1] <= duration
        assert window[1] > window[0]


def test_finalize_approved_keeps_original_and_drops_snippets(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setenv("SERMONPILOT_CLOUD_STAGING_DIR", str(staging))
    staged = staging / "source.mkv"
    staged.write_bytes(b"staged")

    review_dir = _review_dir(tmp_path / "reviews")
    _seed_review(review_dir, staged)

    assert finalize_review_media(review_dir, "approved") is True
    assert review_dir.is_dir()
    assert (review_dir / "Sermon - Original.mp4").is_file()
    assert not (review_dir / "snippets").exists()
    assert not staged.exists()


def test_finalize_failed_keeps_original_but_removes_staged(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setenv("SERMONPILOT_CLOUD_STAGING_DIR", str(staging))
    staged = staging / "source.mkv"
    staged.write_bytes(b"staged")

    review_dir = _review_dir(tmp_path / "reviews", "review-failed")
    _seed_review(review_dir, staged)

    assert finalize_review_media(review_dir, "failed") is True
    assert (review_dir / "Sermon - Original.mp4").is_file()
    assert not (review_dir / "snippets").exists()
    assert not staged.exists()


def test_finalize_discarded_removes_review_dir(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setenv("SERMONPILOT_CLOUD_STAGING_DIR", str(staging))
    staged = staging / "source.mkv"
    staged.write_bytes(b"staged")

    review_dir = _review_dir(tmp_path / "reviews", "review-discarded")
    _seed_review(review_dir, staged)

    assert finalize_review_media(review_dir, "discarded") is True
    assert not review_dir.exists()
    assert not staged.exists()


def test_finalize_refuses_untagged_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_CLOUD_STAGING_DIR", str(tmp_path / "staging"))
    plain = tmp_path / "output" / "Sermon - Original.mp4"
    plain.parent.mkdir(parents=True)
    plain.write_bytes(b"real")

    assert finalize_review_media(plain.parent, "discarded") is False
    assert plain.exists()


def test_finalize_never_deletes_an_unstaged_source(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_CLOUD_STAGING_DIR", str(tmp_path / "staging"))
    real = tmp_path / "real" / "sermon.mkv"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"real")

    review_dir = _review_dir(tmp_path / "reviews", "review-real-source")
    _seed_review(review_dir, real)

    finalize_review_media(review_dir, "discarded")
    assert real.is_file()


def test_render_bounded_snippets_drops_oversized(tmp_path, monkeypatch):
    import src.auto_edit as auto_edit

    monkeypatch.setenv("SERMONPILOT_REVIEW_SNIPPET_MAX_MB", "0.00001")

    def fake_render(source, plan, out_dir, logo_path=None, fade_out_tail_seconds=2.0):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        big = out_dir / "snippet_start.mp4"
        small = out_dir / "snippet_end.mp4"
        big.write_bytes(b"x" * 4096)
        small.write_bytes(b"x" * 8)
        return [big, small]

    monkeypatch.setattr(auto_edit, "render_review_snippets", fake_render)

    kept = render_bounded_snippets(
        tmp_path / "source.mp4", object(), tmp_path / "snippets"
    )

    assert [path.name for path in kept] == ["snippet_end.mp4"]
    assert not (tmp_path / "snippets" / "snippet_start.mp4").exists()


def test_sweep_removes_aged_reviews(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(tmp_path / "reviews"))
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_DAYS", "1")
    monkeypatch.delenv("SERMONPILOT_REVIEW_RETENTION_MAX_GB", raising=False)

    old = _review_dir(tmp_path / "reviews", "old-review")
    _seed_review(old)
    fresh = _review_dir(tmp_path / "reviews", "fresh-review")
    _seed_review(fresh)
    os.utime(old / MARKER_FILENAME, (1, 1))

    result = sweep_abandoned_reviews({"output_directory": str(tmp_path / "out")})

    assert str(old) in result["removed"]
    assert not old.exists()
    assert fresh.is_dir()


def test_sweep_enforces_total_size_cap_oldest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(tmp_path / "reviews"))
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_DAYS", "0")
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_MAX_GB", "0.000006")

    oldest = _review_dir(tmp_path / "reviews", "oldest")
    _seed_review(oldest)
    (oldest / "bulk.bin").write_bytes(b"x" * 4096)
    os.utime(oldest / MARKER_FILENAME, (1, 1))

    newest = _review_dir(tmp_path / "reviews", "newest")
    _seed_review(newest)
    (newest / "bulk.bin").write_bytes(b"x" * 4096)
    os.utime(newest / MARKER_FILENAME, (2, 2))

    result = sweep_abandoned_reviews({"output_directory": str(tmp_path / "out")})

    assert str(oldest) in result["removed"]
    assert not oldest.exists()
    assert newest.is_dir()


def test_sweep_keeps_a_lone_review_larger_than_the_cap(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(tmp_path / "reviews"))
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_DAYS", "0")
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_MAX_GB", "0.000001")

    only = _review_dir(tmp_path / "reviews", "only-review")
    _seed_review(only)
    (only / "bulk.bin").write_bytes(b"x" * 4096)

    with caplog.at_level("WARNING"):
        result = sweep_abandoned_reviews({"output_directory": str(tmp_path / "out")})

    assert only.is_dir()
    assert (only / "bulk.bin").is_file()
    assert str(only) not in result["removed"]
    assert result["kept"] == 1
    warnings = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert any("size cap" in message for message in warnings), warnings


def test_sweep_never_discards_the_protected_current_review(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(tmp_path / "reviews"))
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_DAYS", "0")
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_MAX_GB", "0.000006")

    older = _review_dir(tmp_path / "reviews", "older")
    _seed_review(older)
    (older / "bulk.bin").write_bytes(b"x" * 4096)
    os.utime(older / MARKER_FILENAME, (1, 1))

    current = _review_dir(tmp_path / "reviews", "current")
    _seed_review(current)
    (current / "bulk.bin").write_bytes(b"x" * 4096)
    os.utime(current / MARKER_FILENAME, (2, 2))

    result = sweep_abandoned_reviews(
        {"output_directory": str(tmp_path / "out")}, protect_dir=current
    )

    assert str(current) not in result["removed"]
    assert current.is_dir()
    assert (current / "bulk.bin").is_file()


def test_sweep_protects_current_review_from_the_age_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(tmp_path / "reviews"))
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_DAYS", "1")
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_MAX_GB", "0")

    current = _review_dir(tmp_path / "reviews", "current")
    _seed_review(current)
    os.utime(current / MARKER_FILENAME, (1, 1))

    result = sweep_abandoned_reviews(
        {"output_directory": str(tmp_path / "out")}, protect_dir=current
    )

    assert str(current) not in result["removed"]
    assert current.is_dir()


def test_retention_summary_exposes_bounds(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(tmp_path / "reviews"))
    summary = retention_summary({})
    assert summary["root"] == str(tmp_path / "reviews")
    assert summary["retention_days"] == 7.0
    assert summary["snippet_max_seconds"] == 30.0
