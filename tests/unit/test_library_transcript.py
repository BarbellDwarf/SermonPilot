from __future__ import annotations

import json

from ui.ui_pages.library import _load_local_transcript_files


def test_load_local_transcript_files(tmp_path):
    media = tmp_path / "sermon.mp4"
    media.write_bytes(b"x")
    (tmp_path / "transcript.txt").write_text("plain text", encoding="utf-8")
    (tmp_path / "transcript_timestamps.json").write_text(
        json.dumps([{"start": 65.0, "end": 70.0, "text": "hello"}]),
        encoding="utf-8",
    )
    plain, stamped = _load_local_transcript_files(str(media))
    assert plain == "plain text"
    assert stamped == "[01:05] hello"


def test_timestamped_file_provides_plain_when_txt_missing(tmp_path):
    media = tmp_path / "sermon.mp4"
    media.write_bytes(b"x")
    (tmp_path / "transcript_timestamps.json").write_text(
        json.dumps([{"start": 5.0, "end": 8.0, "text": "only stamps"}]),
        encoding="utf-8",
    )
    plain, stamped = _load_local_transcript_files(str(media))
    assert plain == stamped
    assert "[00:05] only stamps" in plain
