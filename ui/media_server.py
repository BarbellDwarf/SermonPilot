"""Localhost HTTP server for streaming sermon media with Range support."""

from __future__ import annotations

import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".mp3", ".wav", ".m4v", ".webm"}
_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


class MediaServer:
    def __init__(
        self,
        root: str | Path,
        host: str = "127.0.0.1",
        public_host: str | None = None,
        port: int = 0,
    ) -> None:
        self.root = Path(root).resolve()
        self.host = host
        self.public_host = public_host
        self.requested_port = port
        self._tokens: dict[str, str] = {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.base_url = ""
        self.port = 0

    def register(self, sermon_id: str, path: str | Path) -> str:
        token = secrets.token_urlsafe(16)
        with self._lock:
            self._tokens[token] = str(path)
        return token

    def resolve(self, token: str) -> Path | None:
        raw = self._tokens.get(token)
        if not raw:
            return None
        candidate = Path(raw).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            return None
        if candidate.suffix.lower() not in _ALLOWED_EXTENSIONS:
            return None
        try:
            if not candidate.is_file():
                return None
        except OSError:
            return None
        return candidate

    def start(self) -> tuple[str, int]:
        if self._server is None:
            server = _MediaHTTPServer((self.host, self.requested_port), self)
            self._server = server
            self._thread = threading.Thread(target=server.serve_forever, daemon=True)
            self._thread.start()
        port = self._server.server_address[1]
        host = self.public_host or self.host
        self.base_url = f"http://{host}:{port}"
        self.port = port
        return self.base_url, port

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
            self.base_url = ""
            self.port = 0


class _MediaHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], media: MediaServer) -> None:
        super().__init__(address, _MediaHandler)
        self.media = media

    def resolve(self, token: str) -> Path | None:
        return self.media.resolve(token)


class _MediaHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._serve()

    def do_HEAD(self) -> None:
        self._serve()

    def _serve(self) -> None:
        status, file_path, start, end, total = self._resolve_or_fail()
        send_body = self.command == "GET"

        self.send_response(status)
        self.send_header("Accept-Ranges", "bytes")
        if file_path is not None:
            self.send_header("Content-Type", _CONTENT_TYPES.get(file_path.suffix.lower(), ""))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end - 1}/{total}")
        if status == 416:
            self.send_header("Content-Range", f"bytes */{total}")
        self.send_header("Content-Length", str(end - start))
        self.end_headers()
        if send_body and file_path is not None and start < end:
            try:
                with file_path.open("rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(end - start))
            except (ConnectionError, BrokenPipeError, OSError):
                self.close_connection = True

    def _resolve_or_fail(self) -> tuple[int, Path | None, int, int, int]:
        zero = (404, None, 0, 0, 0)
        raw = self.path.split("?", 1)[0].split("#", 1)[0]
        token = raw.removeprefix("/m/").strip("/")
        if not token or raw != "/m/" + token:
            return zero
        file_path = self.server.resolve(token)
        if file_path is None:
            return zero
        try:
            total = file_path.stat().st_size
        except OSError:
            return zero
        start, end = self._parse_range(total)
        if start >= end:
            return 416, file_path, 0, 0, total
        if start == 0 and end == total and not self.headers.get("Range"):
            return 200, file_path, start, end, total
        return 206, file_path, start, end, total

    def _parse_range(self, total: int) -> tuple[int, int]:
        header = self.headers.get("Range", "")
        if not header.startswith("bytes="):
            return 0, total
        spec = header.removeprefix("bytes=").split(",", 1)[0].strip()
        if "-" not in spec:
            return 0, total
        raw_start, _, raw_end = spec.partition("-")
        try:
            start = int(raw_start) if raw_start else 0
            end = int(raw_end) + 1 if raw_end else total
        except ValueError:
            return 0, total
        if raw_start and raw_end:
            end = min(end, total)
        end = max(start, min(end, total))
        return start, end

    def log_message(self, format: str, *args: object) -> None:
        pass


_server: MediaServer | None = None


def start_media_server(
    root: str | Path,
    host: str = "127.0.0.1",
    public_host: str | None = None,
    port: int = 0,
) -> tuple[str, int]:
    global _server
    if _server is None:
        _server = MediaServer(root, host=host, public_host=public_host, port=port)
    return _server.start()


def get_media_server() -> MediaServer | None:
    return _server
