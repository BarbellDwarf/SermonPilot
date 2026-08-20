"""Regression: batch processing invokes per-sermon processing exactly once per sermon.

The batch entry point must call ``process_single_sermon`` once for each
matched sermon, never twice for the same sermon.
"""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import Mock

import sermon_updater as su


def _make_args(**overrides) -> Namespace:
    defaults = {
        "sermon_id": None,
        "year": None,
        "years": None,
        "limit": None,
        "list_only": False,
        "auto_yes": True,
        "verbose": False,
        "dry_run": False,
        "no_upload": False,
        "metadata_only": False,
        "skip_audio": False,
        "force_description": False,
        "force_hashtags": False,
        "no_metadata": False,
        "output_dir": None,
        "save_original_audio": None,
        "save_transcript": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def _make_sermons(count: int) -> list[su.SermonLite]:
    return [
        su.SermonLite(
            sermonID=str(i),
            displayTitle=f"Sermon {i}",
            preachDate="2024-01-01",
            speakerName="Test Speaker",
            eventType="Sunday Service",
        )
        for i in range(1, count + 1)
    ]


def _patch_batch_dependencies(monkeypatch, tmp_path, sermons) -> Mock:
    monkeypatch.setattr(
        su,
        "config",
        {
            "api_key": "test-api-key",
            "broadcaster_id": "test-broadcaster",
            "llm": {"primary": {"provider": "ollama"}},
            "output_directory": str(tmp_path / "output"),
            "save_original_audio": True,
            "save_transcript": False,
        },
    )
    monkeypatch.setattr(su, "fetch_sermons", lambda params, max_results=None: sermons)
    monkeypatch.setattr(su, "confirm", lambda prompt, auto_yes: True)

    class FakeLLM:
        def get_provider_info(self) -> dict:
            return {"primary": None, "fallback": None}

    monkeypatch.setattr(su, "llm_manager", FakeLLM())

    per_sermon = Mock(return_value={"action": "processed", "completed": ["metadata"]})
    monkeypatch.setattr(su, "process_single_sermon", per_sermon)
    monkeypatch.setattr(su.time, "sleep", lambda seconds: None)
    return per_sermon


def test_batch_processing_calls_per_sermon_once(tmp_path, monkeypatch) -> None:
    sermons = _make_sermons(3)
    per_sermon = _patch_batch_dependencies(monkeypatch, tmp_path, sermons)

    su.handle_original_processing(_make_args())

    assert per_sermon.call_count == len(sermons)
    processed_ids = [call.args[0] for call in per_sermon.call_args_list]
    assert processed_ids == ["1", "2", "3"]


def test_batch_processing_list_only_does_not_process(tmp_path, monkeypatch) -> None:
    sermons = _make_sermons(2)
    per_sermon = _patch_batch_dependencies(monkeypatch, tmp_path, sermons)

    su.handle_original_processing(_make_args(list_only=True))

    per_sermon.assert_not_called()
