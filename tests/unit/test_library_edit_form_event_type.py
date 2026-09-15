"""Library edit form renders the event-type picker and submits its value.

Regression coverage for the Edit dialog on the Library detail: the
event-type selectbox must render inside the ``st.form`` (label visible,
stored value preselected) and a Save must persist the picked value. A
changed stored value must remount the widget preselected to the new value
instead of showing stale session state.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import ui.sermon_metadata as metadata  # noqa: E402
from ui.ui_pages import library  # noqa: E402

ALLOWED = ["Sunday Service", "Bible Study"]


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeSt:
    """Recording stand-in with real form/column context-manager semantics."""

    def __init__(self, save_clicked: bool = False) -> None:
        self.calls: list[tuple] = []
        self.session_state: dict = {}
        self.save_clicked = save_clicked

    def _rec(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def markdown(self, *a, **k):
        self._rec("markdown", *a, **k)

    def text(self, *a, **k):
        self._rec("text", *a, **k)

    def caption(self, *a, **k):
        self._rec("caption", *a, **k)

    def warning(self, *a, **k):
        self._rec("warning", *a, **k)

    def error(self, *a, **k):
        self._rec("error", *a, **k)

    def success(self, *a, **k):
        self._rec("success", *a, **k)

    def text_input(self, label, value="", **kwargs):
        self._rec("text_input", label, value, **kwargs)
        return value

    def text_area(self, label, value="", **kwargs):
        self._rec("text_area", label, value, **kwargs)
        return value

    def selectbox(self, label, options, index=0, key=None, **kwargs):
        self._rec("selectbox", label, list(options), index=index, key=key, **kwargs)
        chosen = self.session_state.get(key, list(options)[index])
        self.session_state[key] = chosen
        return chosen

    def date_input(self, label, value=None, **kwargs):
        self._rec("date_input", label, value, **kwargs)
        return value or datetime.date(2024, 1, 1)

    def columns(self, spec):
        self._rec("columns", spec)
        n = len(spec) if isinstance(spec, list | tuple) else int(spec)
        return [_Ctx() for _ in range(n)]

    def form(self, key):
        self._rec("form", key)
        return _Ctx()

    def form_submit_button(self, label, **kwargs):
        self._rec("form_submit_button", label, **kwargs)
        return self.save_clicked and label == "Save"

    def rerun(self):
        self._rec("rerun")


class FakeApi:
    def is_configured(self):
        return False


class FakeRepo:
    def __init__(self) -> None:
        self.saved: tuple | None = None

    def update_sermon_metadata(self, sermon_id: str, data: dict) -> bool:
        self.saved = (sermon_id, data)
        return True

    def get_sermon(self, sermon_id: str) -> dict:
        return {"id": sermon_id}


def _sermon(**overrides) -> dict:
    base = {
        "id": "s1",
        "title": "T",
        "speaker": "Spk",
        "recorded_date": "2024-01-01",
        "series_title": "",
        "scripture_reference": "John 3:16",
        "event_type": "Bible Study",
        "description": "d",
    }
    base.update(overrides)
    return base


@pytest.fixture
def fake_st(monkeypatch) -> FakeSt:
    fake = FakeSt()
    monkeypatch.setattr(library, "st", fake)
    monkeypatch.setattr(metadata, "st", fake)
    monkeypatch.setattr(metadata, "get_event_types", lambda: list(ALLOWED))
    return fake


def _event_selectboxes(fake: FakeSt) -> list[tuple]:
    return [
        call for call in fake.calls
        if call[0] == "selectbox" and call[1][0] == "Event Type"
    ]


def test_edit_form_renders_event_type_picker(fake_st: FakeSt) -> None:
    repo = FakeRepo()
    library.display_sermon_editor(_sermon(), FakeApi(), repo)

    picks = _event_selectboxes(fake_st)
    assert len(picks) == 1
    _, args, kwargs = picks[0]
    assert list(args[1]) == ["[Select Event Type]", *ALLOWED]
    assert kwargs["index"] == ALLOWED.index("Bible Study") + 1


def test_edit_form_submit_persists_picked_event_type(
    monkeypatch, fake_st: FakeSt
) -> None:
    picked: dict = {}

    orig_selectbox = fake_st.selectbox

    def _select(label, options, index=0, key=None, **kwargs):
        value = orig_selectbox(label, options, index=index, key=key, **kwargs)
        if label == "Event Type":
            picked["value"] = "Sunday Service"
            fake_st.session_state[key] = "Sunday Service"
            return "Sunday Service"
        return value

    fake_st.selectbox = _select
    fake_st.save_clicked = True

    repo = FakeRepo()
    library.display_sermon_editor(_sermon(), FakeApi(), repo)

    assert repo.saved is not None
    _, data = repo.saved
    assert data["event_type"] == "Sunday Service"
    assert picked["value"] == "Sunday Service"


def test_edit_form_remounts_preselect_when_stored_value_changes(
    monkeypatch, fake_st: FakeSt
) -> None:
    repo = FakeRepo()
    library.display_sermon_editor(_sermon(event_type="Bible Study"), FakeApi(), repo)
    first_key = _event_selectboxes(fake_st)[0][2]["key"]

    fake2 = FakeSt()
    monkeypatch.setattr(library, "st", fake2)
    monkeypatch.setattr(metadata, "st", fake2)
    library.display_sermon_editor(_sermon(event_type="Sunday Service"), FakeApi(), repo)
    second = _event_selectboxes(fake2)[0]

    assert second[2]["key"] != first_key
    assert second[2]["index"] == ALLOWED.index("Sunday Service") + 1
