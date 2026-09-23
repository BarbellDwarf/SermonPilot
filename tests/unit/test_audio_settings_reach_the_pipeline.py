"""The audio settings saved in the console must reach the enhancer.

The console stores ``audio_noise_reduction``, ``audio_amplify``,
``audio_normalize``, ``audio_gain_db`` and ``audio_target_level_db`` and
allowlists them in the config API, so the operator expects a change there to
change what the pipeline does. Before this guard ``process_new_sermon`` called
``processor.process_sermon_audio(input, output)`` with no processing kwargs, so
the enhancer's own defaults won and every audio setting was inert for console
jobs.

These tests drive the real ``process_new_sermon`` with a stubbed processor that
records the kwargs it was handed, once on a fresh run and once on the Library
apply path, and pin the two resolution rules:

- the resolved settings come from the app config under the keys the settings
  page writes, with the enhancer's defaults when a key is absent;
- ``audio_enhancement_method == "none"`` skips enhancement on both paths, even
  when the legacy ``metadata_processing.process_audio`` flag is set, and the log
  names which setting won.
"""

from __future__ import annotations

import json
import logging
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

import sermon_updater as su
import ui.auto_edit_apply as core
from ui.config_utils import ENV_CONFIG_MAP
from ui.database import SermonDatabase, SermonRepository

SID = "draft_audio_cfg_0001"
PLAN_START = 40.0
PLAN_END = 2958.0

AUDIO_SETTINGS = {
    "audio_noise_reduction": False,
    "audio_amplify": False,
    "audio_normalize": False,
    "audio_gain_db": 2.5,
    "audio_target_level_db": -16.0,
}


@pytest.fixture
def repo(tmp_path, monkeypatch) -> SermonRepository:
    db_path = tmp_path / "audio_cfg.db"
    monkeypatch.setenv("DATABASE_URL", str(db_path))
    monkeypatch.setattr("ui.database._db", None)
    return SermonRepository(SermonDatabase(db_path=str(db_path)))


@pytest.fixture
def stub_processor(monkeypatch) -> list[dict]:
    """Record every ``process_sermon_audio`` call the pipeline makes."""
    calls: list[dict] = []
    fake_audio = types.ModuleType("src.audio_processing")

    class _RecordingProcessor:
        enhancement_method = "deepfilternet"

        def __init__(self, method: str = "deepfilternet", *_args, **_kwargs):
            self.enhancement_method = method

        def process_sermon_audio(self, source, out, **kwargs):
            calls.append({"source": str(source), "out": str(out), **kwargs})
            Path(out).write_bytes(b"wav")
            return True, {}

        def release_gpu(self):
            pass

    fake_audio.AudioProcessor = _RecordingProcessor
    monkeypatch.setitem(sys.modules, "src.audio_processing", fake_audio)
    monkeypatch.setattr(su, "generate_title", Mock(return_value="Generated Title"))
    monkeypatch.setattr(su, "generate_summary", Mock(return_value="Generated description"))
    monkeypatch.setattr(su, "generate_hashtags", Mock(return_value="#generated"))
    monkeypatch.setattr(
        su, "transcribe_segments", Mock(return_value=("A transcript.", []))
    )

    def _fake_apply(source, _plan, out, **_kwargs):
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"edited")
        return out

    monkeypatch.setattr(su, "apply_edit", Mock(side_effect=_fake_apply))
    return calls


def _config(tmp_path: Path, **overrides) -> dict:
    config = {
        "output_directory": str(tmp_path / "output"),
        "auto_edit": {"enabled": False, "min_sermon_seconds": 1},
        "dry_run": True,
    }
    config.update(overrides)
    return config


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "raw_audio.mp3"
    source.write_bytes(b"raw")
    return source


def _run_fresh(tmp_path: Path, config: dict) -> dict:
    return su.process_new_sermon(
        audio_file=str(_source(tmp_path)),
        speaker_name="Sample Speaker",
        recorded_date="2024-01-01",
        title="A Title",
        description="A description",
        hashtags="#tag",
        dry_run=True,
        skip_transcription=True,
        config=config,
    )


def _plan_dict() -> dict:
    return {
        "proposed_start": PLAN_START,
        "proposed_end": PLAN_END,
        "confidence": 1.0,
        "needs_review": False,
        "evidence": "approved",
        "qa_judgment": "approved",
        "reasoning": "",
        "status": "pending_review",
        "source_path": "Keeper.mp4",
        "notes": "",
    }


def _seed_apply(repo: SermonRepository, tmp_path: Path) -> tuple[int, Path]:
    directory = tmp_path / "review"
    directory.mkdir()
    original = directory / "Original.mp4"
    original.write_bytes(b"orig")
    metadata = {"sermon_id": SID, "original_file": str(original), "is_video": False}
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    repo.save_sermon(
        {
            "id": SID,
            "title": "Stored Title",
            "speaker": "Sample Speaker",
            "recorded_date": "2024-01-01",
            "status": "draft",
            "edit_status": "pending_review",
            "file_paths": {"audio": str(original), "metadata": str(directory / "metadata.json")},
        }
    )
    plan_id = repo.save_edit_plan_revision(SID, _plan_dict())
    return plan_id, original


def _run_apply(repo: SermonRepository, plan_id: int, tmp_path: Path, config: dict) -> dict:
    return core.run_library_apply(
        repo,
        SID,
        PLAN_START,
        PLAN_END,
        render_only=True,
        plan_id=plan_id,
        config=config,
    )


def test_resolved_audio_settings_reach_the_enhancer_on_a_fresh_run(
    tmp_path, stub_processor
) -> None:
    _run_fresh(tmp_path, _config(tmp_path, **AUDIO_SETTINGS))

    assert stub_processor, "the enhancer should have been asked to process audio"
    kwargs = stub_processor[-1]
    assert kwargs["noise_reduction"] is False
    assert kwargs["amplify"] is False
    assert kwargs["normalize"] is False
    assert kwargs["gain_db"] == pytest.approx(2.5)
    assert kwargs["target_level_db"] == pytest.approx(-16.0)


def test_absent_audio_settings_keep_the_enhancer_defaults(tmp_path, stub_processor) -> None:
    _run_fresh(tmp_path, _config(tmp_path))

    kwargs = stub_processor[-1]
    assert kwargs["noise_reduction"] is True
    assert kwargs["amplify"] is True
    assert kwargs["normalize"] is True
    assert kwargs["gain_db"] == pytest.approx(0.0)
    assert kwargs["target_level_db"] == pytest.approx(-22.0)


def test_fresh_run_and_apply_path_resolve_the_same_audio_settings(
    tmp_path, repo, stub_processor
) -> None:
    config = _config(tmp_path, **AUDIO_SETTINGS)
    _run_fresh(tmp_path, config)
    fresh_kwargs = {
        key: stub_processor[-1][key]
        for key in ("noise_reduction", "amplify", "normalize", "gain_db", "target_level_db")
    }

    plan_id, _source_path = _seed_apply(repo, tmp_path)
    _run_apply(repo, plan_id, tmp_path, config)
    apply_kwargs = {
        key: stub_processor[-1][key]
        for key in ("noise_reduction", "amplify", "normalize", "gain_db", "target_level_db")
    }

    assert apply_kwargs == fresh_kwargs
    assert apply_kwargs["target_level_db"] == pytest.approx(-16.0)
    assert apply_kwargs["normalize"] is False


def test_none_method_skips_on_the_fresh_run_despite_the_legacy_flag(
    tmp_path, stub_processor, caplog
) -> None:
    config = _config(
        tmp_path,
        audio_enhancement_method="none",
        metadata_processing={"process_audio": True},
    )
    with caplog.at_level(logging.INFO, logger="sermon_updater"):
        _run_fresh(tmp_path, config)

    assert stub_processor == [], "method none must skip the enhancer"
    records = [r for r in caplog.records if "enhancement" in r.getMessage().lower()]
    assert records, "the skip must be logged"
    assert any("none" in r.getMessage().lower() for r in records)
    winner = " ".join(r.getMessage().lower() for r in records)
    assert "method" in winner and "none" in winner


def test_none_method_skips_on_the_apply_path_despite_the_legacy_flag(
    tmp_path, repo, stub_processor, caplog
) -> None:
    plan_id, _source_path = _seed_apply(repo, tmp_path)
    config = _config(
        tmp_path,
        audio_enhancement_method="none",
        metadata_processing={"process_audio": True},
    )
    with caplog.at_level(logging.INFO, logger="ui.auto_edit_apply"):
        result = _run_apply(repo, plan_id, tmp_path, config)

    assert result["success"] is True
    assert stub_processor == [], "method none must skip the enhancer"
    records = [
        r.getMessage().lower()
        for r in caplog.records
        if "enhancement" in r.getMessage().lower()
    ]
    assert any("settings have it off" in r for r in records), records


def _enclosing_call_source(source: str, marker: str) -> str:
    """The source of the statement whose call text contains ``marker``.

    Walks backwards to the start of the statement (the previous newline whose
    following line is dedented) and forwards to the matching closing bracket,
    so the guard inspects only the call that must carry the shared settings.
    """
    at = source.index(marker)
    line_start = source.rfind("\n", 0, at)
    while line_start > 0:
        prev_start = source.rfind("\n", 0, line_start) + 1
        if not source[prev_start:line_start].startswith(" "):
            break
        line_start = prev_start - 1
        if line_start <= 0:
            line_start = 0
            break
    line_start = max(line_start, 0) + (1 if line_start > 0 else 0)
    depth = 0
    end = at
    for i in range(source.index("(", at), len(source)):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return source[line_start:end]


def test_source_guard_pins_the_single_audio_settings_resolution() -> None:
    """The caller must not hard-code a processing default of its own."""
    source = Path(su.__file__).resolve().read_text(encoding="utf-8")
    assert "def audio_processing_settings(config" in source, (
        "the shared audio-settings resolver must exist"
    )
    call = _enclosing_call_source(source, "processor.process_sermon_audio(")
    assert "**audio_processing_settings(config)" in call, (
        "the enhancer call must resolve the audio settings through the shared "
        f"helper, got:\n{call}"
    )
    for literal in (
        "noise_reduction=True",
        "amplify=True",
        "normalize=True",
        "target_level_db=-22",
        "gain_db=0",
    ):
        assert literal not in call, (
            f"the enhancer call must not carry a hard-coded audio setting ({literal})"
        )


def test_settings_saved_through_the_api_reach_the_enhancer_kwargs(
    client, scoped_setup, monkeypatch, tmp_path
) -> None:
    """A value written on the console Audio section is what the enhancer gets."""
    for var in ENV_CONFIG_MAP:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("SERMONPILOT_VARIANT", raising=False)
    monkeypatch.setenv("SA_UPDATER_CONFIG", str(tmp_path / "absent-config.yaml"))

    headers = scoped_setup["a"]["headers"]
    saved = client.put(
        "/api/config/sections/audio",
        json={
            "values": {
                "audio_normalize": False,
                "audio_target_level_db": -16.0,
                "audio_noise_reduction": False,
                "audio_gain_db": 2.5,
            }
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text

    from ui.config_utils import resolve_config

    kwargs = su.audio_processing_settings(resolve_config())
    assert kwargs["normalize"] is False
    assert kwargs["target_level_db"] == pytest.approx(-16.0)
    assert kwargs["noise_reduction"] is False
    assert kwargs["gain_db"] == pytest.approx(2.5)
