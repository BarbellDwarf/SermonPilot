from __future__ import annotations

import json

from ui.ui_pages.library import _resolve_apply_source


class _Repo:
    def __init__(self, full: dict | None):
        self._full = full

    def get_sermon(self, _sermon_id):
        return self._full


def test_list_shaped_sermon_resolves_processed_via_full_fetch(tmp_path):
    processed = tmp_path / "Sermon_Processed.mp4"
    processed.write_bytes(b"x")
    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps({"processed_file": str(processed), "original_file": "orig.mp4"}),
        encoding="utf-8",
    )
    full = {
        "id": "s1",
        "file_paths": {"audio": str(processed), "metadata": str(metadata)},
    }
    thin = {"id": "s1", "file_paths": None}
    source, enhanced = _resolve_apply_source(thin, _Repo(full))
    assert source == str(processed)
    assert enhanced is True


def test_missing_metadata_falls_back_to_processed_audio(tmp_path):
    processed = tmp_path / "Sermon_Processed.mp4"
    processed.write_bytes(b"x")
    full = {"id": "s1", "file_paths": {"audio": str(processed)}}
    thin = {"id": "s1"}
    source, enhanced = _resolve_apply_source(thin, _Repo(full))
    assert source == str(processed)
    assert enhanced is True


def test_keeper_audio_is_not_treated_as_enhanced(tmp_path):
    keeper = tmp_path / "Sermon_Processed_keeper.wav"
    keeper.write_bytes(b"x")
    full = {"id": "s1", "file_paths": {"audio": str(keeper)}}
    thin = {"id": "s1"}
    source, enhanced = _resolve_apply_source(thin, _Repo(full))
    assert enhanced is False
