"""Media streaming API: Range support, scoping, and path safety."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _allow_tmp_output_root(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIRECTORY", str(tmp_path))


def _conn():
    from server.api.accounts import get_db_path

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _seed_output_dir(user_id: str, path: Path) -> None:
    from server.api.accounts import set_setting, writable_conn

    with writable_conn() as conn:
        set_setting(conn, user_id, "settings.general", {"output_dir": str(path)})


def _add_file(sermon_id: str, file_type: str, path: Path) -> None:
    conn = _conn()
    try:
        size = path.stat().st_size if path.exists() else 0
        conn.execute(
            "INSERT OR REPLACE INTO sermon_files (sermon_id, file_type, file_path, file_size)"
            " VALUES (?, ?, ?, ?)",
            (sermon_id, file_type, str(path), size),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_media(user_id: str, sermon_id: str, outdir: Path) -> dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    processed = outdir / "sermon - Processed.mp4"
    processed.write_bytes(b"PROCESSED-VIDEO-BYTES" * 10)
    source = outdir / "sermon - Original.mp3"
    source.write_bytes(b"SOURCE-AUDIO-BYTES" * 10)
    transcript = outdir / "transcript.txt"
    transcript.write_text("00:00:01 hello there", encoding="utf-8")
    timestamps = outdir / "transcript_timestamps.json"
    timestamps.write_text(json.dumps([{"start": 1.0, "end": 2.0, "text": "hello there"}]), "utf-8")
    metadata = outdir / "metadata.json"
    metadata.write_text(
        json.dumps({"original_file": str(source), "processed_file": str(processed)}),
        encoding="utf-8",
    )
    _seed_output_dir(user_id, outdir)
    _add_file(sermon_id, "metadata", metadata)
    _add_file(sermon_id, "audio", processed)
    _add_file(sermon_id, "enhanced_audio", source)
    _add_file(sermon_id, "transcript", transcript)
    _add_file(sermon_id, "transcript_timestamps", timestamps)
    return {"processed": processed, "source": source, "transcript": transcript}


def _auth(s: dict, key: str = "a") -> dict[str, str]:
    return s[key]["headers"]


def test_media_listing_reports_available_artifacts(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "a-out"
    _seed_media(s["a"]["id"], "s-a", outdir)
    r = client.get("/api/media/sermons/s-a", headers=_auth(s))
    assert r.status_code == 200, r.text
    body = r.json()
    kinds = {item["kind"]: item for item in body["items"]}
    assert kinds["processed"]["available"] is True
    assert kinds["source"]["available"] is True
    assert kinds["transcript"]["available"] is True
    assert kinds["keeper"]["available"] is False
    assert body["primary"] == "processed"


def test_stream_200_sets_accept_ranges_and_content_type(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "a-out"
    media = _seed_media(s["a"]["id"], "s-a", outdir)
    r = client.get("/api/media/sermons/s-a/processed", headers=_auth(s))
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-type"].startswith("video/mp4")
    assert r.content == media["processed"].read_bytes()
    assert r.headers["content-length"] == str(len(r.content))


def test_stream_206_for_all_three_range_forms(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "a-out"
    media = _seed_media(s["a"]["id"], "s-a", outdir)
    data = media["processed"].read_bytes()
    total = len(data)

    bounded = client.get(
        "/api/media/sermons/s-a/processed", headers={**_auth(s), "Range": "bytes=5-14"}
    )
    assert bounded.status_code == 206
    assert bounded.headers["content-range"] == f"bytes 5-14/{total}"
    assert bounded.headers["content-length"] == "10"
    assert bounded.content == data[5:15]

    open_ended = client.get(
        "/api/media/sermons/s-a/processed", headers={**_auth(s), "Range": "bytes=10-"}
    )
    assert open_ended.status_code == 206
    assert open_ended.headers["content-range"] == f"bytes 10-{total - 1}/{total}"
    assert open_ended.content == data[10:]

    suffix = client.get(
        "/api/media/sermons/s-a/processed", headers={**_auth(s), "Range": "bytes=-7"}
    )
    assert suffix.status_code == 206
    assert suffix.headers["content-range"] == f"bytes {total - 7}-{total - 1}/{total}"
    assert suffix.content == data[-7:]


def test_stream_head_returns_headers_without_body(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "a-out"
    media = _seed_media(s["a"]["id"], "s-a", outdir)
    r = client.head("/api/media/sermons/s-a/processed", headers=_auth(s))
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == str(media["processed"].stat().st_size)
    assert r.content == b""

    partial = client.head(
        "/api/media/sermons/s-a/processed", headers={**_auth(s), "Range": "bytes=0-9"}
    )
    assert partial.status_code == 206
    assert partial.headers["content-length"] == "10"
    assert partial.headers["content-range"].startswith("bytes 0-9/")


def test_stream_416_for_unsatisfiable_range(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "a-out"
    media = _seed_media(s["a"]["id"], "s-a", outdir)
    total = media["processed"].stat().st_size
    r = client.get(
        "/api/media/sermons/s-a/processed", headers={**_auth(s), "Range": "bytes=999999-"}
    )
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{total}"


def test_stream_missing_artifact_returns_json_404(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "a-out"
    _seed_media(s["a"]["id"], "s-a", outdir)
    r = client.get("/api/media/sermons/s-a/keeper", headers=_auth(s))
    assert r.status_code == 404
    assert "keeper" in r.json()["detail"]
    assert r.headers["content-type"].startswith("application/json")


def test_stream_unknown_kind_returns_404(client, scoped_setup, tmp_path):
    s = scoped_setup
    _seed_media(s["a"]["id"], "s-a", tmp_path / "a-out")
    r = client.get("/api/media/sermons/s-a/nonsense", headers=_auth(s))
    assert r.status_code == 404


def test_stream_rejects_path_outside_allowed_roots(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "a-out"
    _seed_media(s["a"]["id"], "s-a", outdir)
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    outside = outside_dir / "outside-secret.mp4"
    outside.write_bytes(b"top secret")
    _add_file("s-a", "audio", outside)
    conn = _conn()
    try:
        conn.execute(
            "DELETE FROM sermon_files WHERE sermon_id = ?"
            " AND file_type IN ('metadata', 'enhanced_audio')",
            ("s-a",),
        )
        conn.commit()
    finally:
        conn.close()
    r = client.get("/api/media/sermons/s-a/processed", headers=_auth(s))
    assert r.status_code == 403
    assert "allowed roots" in r.json()["detail"]


def test_cross_user_stream_denied(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "b-out"
    _seed_media(s["b"]["id"], "s-b", outdir)
    r = client.get("/api/media/sermons/s-b/processed", headers=_auth(s, "a"))
    assert r.status_code == 404
    r2 = client.get("/api/media/sermons/s-b", headers=_auth(s, "a"))
    assert r2.status_code == 404


def test_query_token_authenticates_media_stream(client, scoped_setup, tmp_path):
    s = scoped_setup
    _seed_media(s["a"]["id"], "s-a", tmp_path / "a-out")
    token = client.post(
        "/api/auth/login", json={"username": "user-a", "password": "pw-user-a"}
    ).json()["token"]
    r = client.get(f"/api/media/sermons/s-a/processed?token={token}")
    assert r.status_code == 200
    assert client.get("/api/media/sermons/s-a/processed").status_code == 401


def test_large_file_partial_request_is_206(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "a-out"
    outdir.mkdir(parents=True, exist_ok=True)
    big = outdir / "big - Processed.mp4"
    size = 130 * 1024 * 1024
    with big.open("wb") as handle:
        handle.truncate(size)
        handle.seek(0)
        handle.write(b"HEADER")
        handle.seek(size - 8)
        handle.write(b"TAILMARK")
    _seed_output_dir(s["a"]["id"], outdir)
    _add_file("s-a", "audio", big)
    r = client.get(
        "/api/media/sermons/s-a/processed", headers={**_auth(s), "Range": "bytes=0-1023"}
    )
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 0-1023/{size}"
    assert r.headers["content-length"] == "1024"
    assert len(r.content) == 1024
    assert r.content[:6] == b"HEADER"

    tail = client.get(
        "/api/media/sermons/s-a/processed", headers={**_auth(s), "Range": "bytes=-8"}
    )
    assert tail.status_code == 206
    assert tail.content == b"TAILMARK"


def test_parse_range_forms():
    import pytest

    from server.api.routers.media import RangeNotSatisfiable, parse_range

    assert parse_range(None, 100) is None
    assert parse_range("bytes=0-9", 100) == (0, 10)
    assert parse_range("bytes=10-", 100) == (10, 100)
    assert parse_range("bytes=-10", 100) == (90, 100)
    assert parse_range("not-a-range", 100) is None
    with pytest.raises(RangeNotSatisfiable):
        parse_range("bytes=200-", 100)
    with pytest.raises(RangeNotSatisfiable):
        parse_range("bytes=-0", 100)
