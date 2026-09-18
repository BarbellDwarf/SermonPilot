"""Applied-local adjust panel: no upload offer before first upload.

Drives ``show_edit_review_panel`` with a recording ``st`` stand-in. A draft
whose plan is ``applied_local`` with no ``upload_info`` rows (neither the
sermon nor its rendered record) must not offer render+upload: the only
actions are Upload now plus a clearly-labeled local Re-render. Once an
upload row exists, the genuine re-apply flow keeps the render/upload choice.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ui.ui_pages import library  # noqa: E402


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeSt:
    """Recording streamlit stand-in; widgets return deterministic values."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.session_state: dict = {}

    def _rec(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def _noop(*args, **kwargs):
            self._rec(name, *args, **kwargs)
            return None

        return _noop

    def columns(self, spec):
        self._rec("columns", spec)
        n = len(spec) if isinstance(spec, list | tuple) else int(spec)
        return [_Ctx() for _ in range(n)]

    def container(self, *args, **kwargs):
        self._rec("container", *args, **kwargs)
        return _Ctx()

    def spinner(self, *args, **kwargs):
        self._rec("spinner", *args, **kwargs)
        return _Ctx()

    def checkbox(self, *args, **kwargs):
        self._rec("checkbox", *args, **kwargs)
        return False

    def button(self, label, **kwargs):
        self._rec("button", label, **kwargs)
        return False

    def number_input(self, label, value=0.0, **kwargs):
        self._rec("number_input", label, value=value, **kwargs)
        return value

    def radio(self, label, options, index=0, **kwargs):
        self._rec("radio", label, list(options), index=index, **kwargs)
        return list(options)[index]

    def text_input(self, label, value="", **kwargs):
        self._rec("text_input", label, value=value, **kwargs)
        return ""

    def selectbox(self, label, options, index=0, **kwargs):
        self._rec("selectbox", label, list(options), index=index, **kwargs)
        return list(options)[index]

    def rerun(self):
        self._rec("rerun")


def _plan() -> dict:
    return {
        "id": 1,
        "revision": 2,
        "proposed_start": 10.0,
        "proposed_end": 60.0,
        "final_start": 10.0,
        "final_end": 60.0,
        "confidence": 0.9,
        "needs_review": False,
        "evidence": "e",
        "qa_judgment": "cut",
        "reasoning": "r",
        "audio_offset": 0.0,
        "status": "applied_local",
        "source_path": None,
        "applied_media_id": "draft_rendered_9",
        "notes": "",
    }


class FakeRepo:
    """Minimal repo double: applied_local plan, configurable upload rows."""

    def __init__(self, uploaded_ids: set[str] | None = None) -> None:
        self.uploaded_ids = set(uploaded_ids or set())

    def get_current_edit_plan(self, sermon_id: str) -> dict:
        return _plan()

    def get_edit_plan_history(self, sermon_id: str) -> list[dict]:
        return [_plan()]

    def get_latest_apply_job(self, sermon_id: str):
        return None

    def get_apply_jobs_by_status(self, job_type: str, statuses: list[str]):
        return []

    def get_sermon(self, sermon_id: str):
        if sermon_id in self.uploaded_ids:
            return {"id": sermon_id, "upload_info": {"sermonaudio_id": "123"}}
        return None


def _render(sermon: dict, repo: FakeRepo, monkeypatch) -> FakeSt:
    fake = FakeSt()
    monkeypatch.setattr(library, "st", fake)
    monkeypatch.setattr("ui.database.SermonRepository", lambda *a, **k: repo)
    library.show_edit_review_panel(sermon)
    return fake


def _radios(fake: FakeSt) -> list[tuple]:
    return [c for c in fake.calls if c[0] == "radio"]


def _buttons(fake: FakeSt) -> list[tuple]:
    return [c for c in fake.calls if c[0] == "button"]


def test_pre_upload_offers_no_upload_target(monkeypatch) -> None:
    """Un-uploaded applied_local draft: no upload option, Re-render instead."""
    sermon = {"id": "draft_live_1", "title": "T", "duration": 120.0}
    fake = _render(sermon, FakeRepo(), monkeypatch)

    labels = [args[0] for _, args, _ in _buttons(fake)]
    assert "Upload now" in labels

    re_target_radios = [
        c for c in _radios(fake) if "upload" in str(c[2].get("key", ""))
        or "Apply target" in str(c[1])
    ]
    assert re_target_radios == []

    assert "Re-render (no upload)" in labels
    assert "Apply adjusted edit" not in labels


def test_post_upload_keeps_render_upload_choice(monkeypatch) -> None:
    """Uploaded sermon re-rendered locally keeps the render/upload choice."""
    sermon = {"id": "922607137246", "title": "T", "duration": 120.0}
    repo = FakeRepo(uploaded_ids={"922607137246"})
    fake = _render(sermon, repo, monkeypatch)

    target_radios = [c for c in _radios(fake) if "Apply target" in str(c[1])]
    assert len(target_radios) == 1
    _, args, kwargs = target_radios[0]
    assert list(args[1]) == ["render_only", "upload"]
    assert kwargs["index"] == 1

    labels = [args[0] for _, args, _ in _buttons(fake)]
    assert "Apply adjusted edit" in labels


def test_post_upload_via_rendered_record_keeps_choice(monkeypatch) -> None:
    """Upload now publishes the rendered record: its row counts as uploaded."""
    sermon = {"id": "draft_live_1", "title": "T", "duration": 120.0}
    repo = FakeRepo(uploaded_ids={"draft_rendered_9"})
    fake = _render(sermon, repo, monkeypatch)

    target_radios = [c for c in _radios(fake) if "Apply target" in str(c[1])]
    assert len(target_radios) == 1
    assert list(target_radios[0][1][1]) == ["render_only", "upload"]
