"""New Sermon form responsiveness: duration probe caps and cache stability.

Seams under test (public boundaries):
- ui.ui_pages.new_sermon_enhanced._get_media_duration (duration probe seam)
- module-level caps DURATION_PROBE_MAX_BYTES / PREVIEW_MAX_BYTES (policy seam)
- _duration_cache_key (cache-key stability seam)

Spec: files over 50MB must never hit the temp-write + ffprobe path;
small-file probes cache on file identity (name+size) so metadata keystrokes
never re-probe; previews cap at 25MB and mount only on explicit user opt-in.
"""

from __future__ import annotations

import pytest

EXPECTED_DURATION_CAP = 50 * 1024 * 1024
EXPECTED_PREVIEW_CAP = 25 * 1024 * 1024


class FakeUpload:
    def __init__(self, name: str, size: int) -> None:
        self.name = name
        self.size = size
        self.type = "audio/mpeg"
        self.getvalue_calls = 0

    def getvalue(self) -> bytes:
        self.getvalue_calls += 1
        return b"fake-bytes"


def _load_nse(monkeypatch) -> object:
    import streamlit as st

    monkeypatch.setattr(st, "session_state", {}, raising=False)
    import ui.ui_pages.new_sermon_enhanced as nse

    return nse


def test_duration_cap_is_50mb(monkeypatch) -> None:
    nse = _load_nse(monkeypatch)
    assert nse.DURATION_PROBE_MAX_BYTES == EXPECTED_DURATION_CAP


def test_preview_cap_is_25mb(monkeypatch) -> None:
    nse = _load_nse(monkeypatch)
    assert nse.PREVIEW_MAX_BYTES == EXPECTED_PREVIEW_CAP


def test_duration_skips_big_files_without_touching_bytes(monkeypatch) -> None:
    nse = _load_nse(monkeypatch)
    import streamlit as st

    big = FakeUpload("mega_sermon.mp4", 51 * 1024 * 1024)
    run_calls: list = []
    monkeypatch.setattr(
        nse.subprocess, "run", lambda *a, **k: run_calls.append(1) or (_ for _ in ()).throw(
            AssertionError("ffprobe must not run for big files")
        ),
    )

    assert nse._get_media_duration(big) is None
    assert big.getvalue_calls == 0
    assert run_calls == []
    assert all("mega_sermon" not in k for k in st.session_state.keys())


def test_duration_probes_small_files_and_caches(monkeypatch) -> None:
    nse = _load_nse(monkeypatch)

    small = FakeUpload("small.mp3", 1024)
    calls: list = []

    class _Result:
        returncode = 0
        stdout = '{"format": {"duration": "120.0"}}'

    monkeypatch.setattr(nse.subprocess, "run", lambda *a, **k: calls.append(1) or _Result())

    first = nse._get_media_duration(small)
    assert first == pytest.approx(2.0)
    assert small.getvalue_calls == 1
    assert len(calls) == 1

    second = nse._get_media_duration(small)
    assert second == pytest.approx(2.0)
    assert small.getvalue_calls == 1
    assert len(calls) == 1


def test_cache_key_stable_across_metadata_edits(monkeypatch) -> None:
    nse = _load_nse(monkeypatch)
    import streamlit as st

    key_before = nse._duration_cache_key("sermon.mp3", 12345)
    st.session_state["sermon_title"] = "First keystroke"
    st.session_state["bible_text"] = "John 3:16"
    key_after = nse._duration_cache_key("sermon.mp3", 12345)
    assert key_before == key_after

    small = FakeUpload("sermon.mp3", 12345)

    class _Result:
        returncode = 0
        stdout = '{"format": {"duration": "60.0"}}'

    calls: list = []
    monkeypatch.setattr(nse.subprocess, "run", lambda *a, **k: calls.append(1) or _Result())
    assert nse._get_media_duration(small) == pytest.approx(1.0)

    st.session_state["sermon_title"] = "Second keystroke entirely different"
    st.session_state["sermon_hashtags"] = "#faith"
    assert nse._get_media_duration(small) == pytest.approx(1.0)
    assert len(calls) == 1
    assert small.getvalue_calls == 1


def test_preview_gate_rejects_over_cap(monkeypatch) -> None:
    nse = _load_nse(monkeypatch)
    assert nse._should_show_preview(EXPECTED_PREVIEW_CAP) is True
    assert nse._should_show_preview(EXPECTED_PREVIEW_CAP + 1) is False


def test_metadata_form_runs_in_fragment(monkeypatch) -> None:
    nse = _load_nse(monkeypatch)
    assert hasattr(nse, "_show_form_fragment")
