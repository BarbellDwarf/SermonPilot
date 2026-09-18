from __future__ import annotations

from ui.ui_pages.jobs import format_job_parameter_groups


def _flatten(groups: list[tuple[str, list[str]]]) -> list[str]:
    return [line for _, lines in groups for line in lines]


def test_apply_params_show_range_offset_and_mode() -> None:
    params = {
        "sermon_id": "sermon-123",
        "start": 40.0,
        "end": 2958.0,
        "audio_offset": 0.9,
        "render_only": True,
        "source": "/data/media/episode.mp4",
    }
    lines = _flatten(format_job_parameter_groups(params, "auto_edit_apply"))
    assert "Start: 0:40" in lines
    assert "End: 49:18" in lines
    assert "Audio offset: +0.9s" in lines
    assert "Mode: Render only" in lines
    assert "Source: episode.mp4" in lines


def test_apply_zero_offset_and_upload_mode() -> None:
    params = {"start": 0.0, "end": 65.0, "audio_offset": 0.0, "render_only": False}
    lines = _flatten(format_job_parameter_groups(params, "auto_edit_apply"))
    assert "Audio offset: none" in lines
    assert "Mode: Render + upload" in lines


def test_legacy_params_still_render() -> None:
    params = {
        "sermon_ids": ["a", "b"],
        "actions": ["enhance", "transcribe"],
        "whisper_model": "base",
        "dry_run": True,
    }
    lines = _flatten(format_job_parameter_groups(params, "batch_processing"))
    assert "Sermons: 2" in lines
    assert "Actions: enhance, transcribe" in lines
    assert "Whisper Model: base" in lines
    assert "Dry Run: True" in lines


def test_generic_fallback_shows_basename_and_skips_long_paths() -> None:
    params = {
        "source": "/data/media/nested/episode.mp4",
        "custom_flag": "yes",
        "unrelated_blob": "/x/" + "y" * 100,
    }
    groups = format_job_parameter_groups(params, "some_new_type")
    assert groups
    lines = _flatten(groups)
    assert any("episode.mp4" in line for line in lines)
    assert any("Custom Flag: yes" in line for line in lines)
    assert all("y" * 20 not in line for line in lines)


def test_empty_params_hide_section() -> None:
    assert format_job_parameter_groups({}) == []
    assert format_job_parameter_groups(None) == []
    assert format_job_parameter_groups({"form_data": {"a": 1}, "config": {"b": 2}}) == []
