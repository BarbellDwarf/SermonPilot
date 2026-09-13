from __future__ import annotations

import http.client
from pathlib import Path

import pytest

from ui.media_server import MediaServer, get_media_server, start_media_server


@pytest.fixture()
def media_server(tmp_path: Path) -> MediaServer:
    payload = b"0123456789"
    (tmp_path / "clip.mp4").write_bytes(payload)
    (tmp_path / "notes.txt").write_bytes(b"secret")
    server = MediaServer(tmp_path)
    yield server
    server.shutdown()


def _get(port: int, target: str, headers: dict[str, str] | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", target, headers=headers or {})
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        conn.close()


def _head(port: int, target: str):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("HEAD", target)
        response = conn.getresponse()
        body = response.read()
        return response.status, dict(response.getheaders()), body
    finally:
        conn.close()


def test_register_returns_token(tmp_path: Path) -> None:
    server = MediaServer(tmp_path)
    media = tmp_path / "clip.mp4"
    token = server.register("sermon-1", media)
    assert token
    first = server.register("sermon-1", media)
    second = server.register("sermon-1", media)
    assert first != second


def test_resolve_within_root(tmp_path: Path) -> None:
    server = MediaServer(tmp_path)
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"0123456789")
    token = server.register("s", media)
    assert server.resolve(token) == media


def test_resolve_unknown_token(tmp_path: Path) -> None:
    server = MediaServer(tmp_path)
    assert server.resolve("not-a-token") is None


def test_resolve_rejects_path_outside_root(tmp_path: Path) -> None:
    outside = Path(tmp_path.parent) / "outside.mp4"
    outside.write_bytes(b"x")
    server = MediaServer(tmp_path)
    token = server.register("s", outside)
    assert server.resolve(token) is None


def test_resolve_rejects_bad_extension(tmp_path: Path) -> None:
    server = MediaServer(tmp_path)
    token = server.register("s", tmp_path / "notes.txt")
    assert server.resolve(token) is None


def test_full_get_200(media_server: MediaServer) -> None:
    base, port = media_server.start()
    assert base.startswith("http://127.0.0.1:")
    media = media_server.root / "clip.mp4"
    token = media_server.register("s", media)
    status, headers, body = _get(port, f"/m/{token}")
    assert status == 200
    assert body == b"0123456789"
    assert headers.get("Content-Type") == "video/mp4"
    assert headers.get("Content-Length") == "10"
    assert headers.get("Accept-Ranges") == "bytes"


def test_partial_range_206_content_range(media_server: MediaServer) -> None:
    _, port = media_server.start()
    token = media_server.register("s", media_server.root / "clip.mp4")
    status, headers, body = _get(port, f"/m/{token}", {"Range": "bytes=2-5"})
    assert status == 206
    assert headers.get("Content-Range") == "bytes 2-5/10"
    assert headers.get("Content-Length") == "4"
    assert body == b"2345"


def test_open_ended_range(media_server: MediaServer) -> None:
    _, port = media_server.start()
    token = media_server.register("s", media_server.root / "clip.mp4")
    status, headers, body = _get(port, f"/m/{token}", {"Range": "bytes=7-"})
    assert status == 206
    assert headers.get("Content-Range") == "bytes 7-9/10"
    assert body == b"789"


def test_range_end_beyond_size_clamped(media_server: MediaServer) -> None:
    _, port = media_server.start()
    token = media_server.register("s", media_server.root / "clip.mp4")
    status, headers, body = _get(port, f"/m/{token}", {"Range": "bytes=0-999"})
    assert status == 206
    assert headers.get("Content-Range") == "bytes 0-9/10"
    assert body == b"0123456789"


def test_unknown_token_is_404(media_server: MediaServer) -> None:
    _, port = media_server.start()
    status, _, body = _get(port, "/m/deadbeef0000")
    assert status == 404
    assert body == b""


def test_traversal_is_404(media_server: MediaServer) -> None:
    outside = media_server.root.parent / "escape.mp4"
    outside.write_bytes(b"nope")
    _, port = media_server.start()
    token = media_server.register("s", outside)
    status, _, _ = _get(port, f"/m/{token}")
    assert status == 404
    status, _, _ = _get(port, "/m/../m/../etc/passwd")
    assert status == 404


def test_bad_extension_is_404(media_server: MediaServer, tmp_path: Path) -> None:
    _, port = media_server.start()
    token = media_server.register("s", tmp_path / "notes.txt")
    status, _, body = _get(port, f"/m/{token}")
    assert status == 404
    assert body == b""


def test_head_has_no_body(media_server: MediaServer) -> None:
    _, port = media_server.start()
    token = media_server.register("s", media_server.root / "clip.mp4")
    status, headers, body = _head(port, f"/m/{token}")
    assert status == 200
    assert body == b""
    assert headers.get("Content-Length") == "10"


def test_root_is_resolved_localhost_only(tmp_path: Path) -> None:
    server = MediaServer(tmp_path)
    _, port = server.start()
    try:
        assert 0 < port < 65536
    finally:
        server.shutdown()


def test_singleton_start_is_idempotent(tmp_path: Path) -> None:
    import ui.media_server as mod

    first = start_media_server(tmp_path)
    base, port = start_media_server(tmp_path)
    assert (base, port) == first
    assert get_media_server().port == port
    mod._server = None
