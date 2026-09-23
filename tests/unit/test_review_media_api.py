"""A paused interactive auto-edit keeps its media streamable through the API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import sermon_updater as su


def _set_output_dir(user_id: str, path: Path) -> None:
    from server.api.accounts import set_setting, writable_conn

    with writable_conn() as conn:
        set_setting(conn, user_id, "settings.general", {"output_dir": str(path)})


def _run_pending_review(
    tmp_path: Path, monkeypatch, *, dry_run: bool, review_root: Path
) -> tuple[dict, Mock, Mock]:
    from src.auto_edit import EditPlan

    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(review_root))
    video = tmp_path / "sermon.mp4"
    video.write_bytes(b"fake video bytes")
    cfg = {
        "output_directory": str(tmp_path / "output"),
        "auto_edit": {"enabled": False, "min_sermon_seconds": 1, "qa_margin_seconds": 3.0},
    }
    monkeypatch.setattr(su, "config", cfg)
    monkeypatch.setattr(
        su,
        "transcribe_segments",
        Mock(return_value=[{"start": 0.0, "end": 120.0, "text": "teaching"}]),
    )
    monkeypatch.setattr(
        su,
        "detect_cut_points",
        Mock(
            return_value=EditPlan(
                start=30.0, end=600.0, confidence=0.9, needs_review=False, evidence="quotes"
            )
        ),
    )
    create = Mock(return_value="111")
    upload = Mock(return_value=True)
    monkeypatch.setattr(su, "create_new_sermon_api", create)
    monkeypatch.setattr(su, "upload_media_file", upload)

    result = su.process_new_sermon(
        str(video),
        speaker_name=f"Review Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        dry_run=dry_run,
        skip_audio=True,
        auto_edit_mode="interactive",
    )
    return result, create, upload


def test_pending_review_media_is_streamable(client, scoped_setup, tmp_path, monkeypatch):
    review_root = tmp_path / "reviews"
    _set_output_dir(scoped_setup["admin_id"], review_root)

    result, create, upload = _run_pending_review(
        tmp_path, monkeypatch, dry_run=False, review_root=review_root
    )

    assert result["edit_plan_status"] == "pending_review"
    create.assert_not_called()
    upload.assert_not_called()

    sermon_id = result["sermon_id"]
    headers = scoped_setup["admin_headers"]
    body = client.get(f"/api/media/sermons/{sermon_id}", headers=headers).json()
    kinds = {item["kind"]: item for item in body["items"]}
    assert kinds["source"]["available"] is True
    assert kinds["processed"]["available"] is True
    assert kinds["transcript"]["available"] is True
    assert body["primary"] == "processed"

    streamed = client.get(f"/api/media/sermons/{sermon_id}/source", headers=headers)
    assert streamed.status_code == 200
    assert streamed.content == b"fake video bytes"


def test_pending_review_records_playable_snippets(client, scoped_setup, tmp_path, monkeypatch):
    from src import review_media

    def fake_render(source, plan, out_dir, logo_path=None, fade_out_tail_seconds=2.0):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for name in review_media.SNIPPET_FILES:
            path = out_dir / name
            path.write_bytes(b"clip")
            paths.append(path)
        return paths

    monkeypatch.setattr(review_media, "render_bounded_snippets", fake_render)
    review_root = tmp_path / "reviews"
    _set_output_dir(scoped_setup["admin_id"], review_root)

    result, create, upload = _run_pending_review(
        tmp_path, monkeypatch, dry_run=False, review_root=review_root
    )

    sermon_id = result["sermon_id"]
    body = client.get(
        f"/api/media/sermons/{sermon_id}", headers=scoped_setup["admin_headers"]
    ).json()
    kinds = {item["kind"]: item for item in body["items"]}
    for kind in ("snippet_start", "snippet_end", "snippet_ending"):
        assert kinds[kind]["available"] is True, kind


def test_dry_run_review_makes_no_api_calls_and_keeps_media(
    client, scoped_setup, tmp_path, monkeypatch
):
    review_root = tmp_path / "reviews"
    _set_output_dir(scoped_setup["admin_id"], review_root)

    result, create, upload = _run_pending_review(
        tmp_path, monkeypatch, dry_run=True, review_root=review_root
    )

    assert result["edit_plan_status"] == "pending_review"
    create.assert_not_called()
    upload.assert_not_called()

    body = client.get(
        f"/api/media/sermons/{result['sermon_id']}", headers=scoped_setup["admin_headers"]
    ).json()
    kinds = {item["kind"]: item for item in body["items"]}
    assert kinds["source"]["available"] is True


def test_pause_with_keeper_retains_media_and_skips_processed_copy(tmp_path, monkeypatch):
    import json

    from src import auto_edit as auto_edit_mod
    from src import review_media
    from src.auto_edit import EditPlan

    review_root = tmp_path / "reviews"
    monkeypatch.setenv("SERMONPILOT_REVIEW_MEDIA_DIR", str(review_root))
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_DAYS", "0")
    monkeypatch.setenv("SERMONPILOT_REVIEW_RETENTION_MAX_GB", "0.000001")

    def fake_keeper(source, out, config, **_kwargs):
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"k" * 8192)
        return out

    def fake_snippets(source, plan, out_dir, logo_path=None, fade_out_tail_seconds=2.0):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "snippet_start.mp4"
        path.write_bytes(b"clip")
        return [path]

    monkeypatch.setattr(auto_edit_mod, "transcode_to_keeper", fake_keeper)
    monkeypatch.setattr(review_media, "render_bounded_snippets", fake_snippets)

    video = tmp_path / "sermon.mp4"
    video.write_bytes(b"fake video bytes")
    cfg = {
        "output_directory": str(tmp_path / "output"),
        "auto_edit": {"enabled": False, "min_sermon_seconds": 1, "qa_margin_seconds": 3.0},
    }
    monkeypatch.setattr(su, "config", cfg)
    monkeypatch.setattr(
        su,
        "transcribe_segments",
        Mock(return_value=[{"start": 0.0, "end": 120.0, "text": "teaching"}]),
    )
    monkeypatch.setattr(
        su,
        "detect_cut_points",
        Mock(
            return_value=EditPlan(
                start=30.0, end=600.0, confidence=0.9, needs_review=False, evidence="quotes"
            )
        ),
    )
    monkeypatch.setattr(su, "create_new_sermon_api", Mock(return_value="111"))
    monkeypatch.setattr(su, "upload_media_file", Mock(return_value=True))

    result = su.process_new_sermon(
        str(video),
        speaker_name=f"Review Speaker {tmp_path.name}",
        recorded_date="2024-01-01",
        dry_run=True,
        auto_edit_mode="interactive",
    )

    assert result["edit_plan_status"] == "pending_review"
    review_dir = Path(result["output_dir"])
    assert review_dir.is_dir()
    assert any(review_dir.iterdir())

    metadata = json.loads((review_dir / "metadata.json").read_text(encoding="utf-8"))
    keeper_file = metadata.get("keeper_file")
    assert keeper_file, metadata
    assert Path(keeper_file).is_file()
    assert Path(keeper_file).parent == review_dir

    assert not list(review_dir.glob("*Processed*"))
    assert "processed_file" not in metadata
