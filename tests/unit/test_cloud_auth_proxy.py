from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from server.api.routers import cloud

URL_LINE = (
    "2026/09/18 21:45:25 NOTICE: Please go to the following link: "
    "http://127.0.0.1:53682/auth?state=xpVTS69pf5uBqVw4Pf60VA\n"
)
TOKEN_LINE = (
    "Paste the following into your remote machine --->\n"
    '{"access_token":"ya29.abc","token_type":"Bearer","refresh_token":"1//xyz"}\n'
    "<---End paste\n"
)


class _FakeProc:
    def __init__(self, lines: list[str]) -> None:
        self.stdout = list(lines)
        self.pid = 4242
        self.killed = False

    def poll(self) -> int | None:
        return 0 if self.killed else None

    def kill(self) -> None:
        self.killed = True


@pytest.fixture(autouse=True)
def _cloud_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    cloud._SESSIONS.clear()
    yield
    cloud._SESSIONS.clear()


def _stub_rclone(monkeypatch, lines_per_call: list[list[str]]) -> None:
    calls = iter(lines_per_call)
    monkeypatch.setattr(cloud.shutil, "which", lambda _name: "/usr/bin/rclone")
    monkeypatch.setattr(cloud.subprocess, "Popen", lambda *a, **k: _FakeProc(next(calls)))


def test_auth_url_uses_request_host_and_session_key(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, [[URL_LINE, TOKEN_LINE]])
    r = client.get(
        "/api/cloud/auth-url",
        params={"provider": "drive", "name": "mydrive"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    key = cloud._session_key(s["a"]["id"], "mydrive")
    assert r.json()["url"] == (
        f"http://testserver/rclone-auth/{key}/auth?state=xpVTS69pf5uBqVw4Pf60VA"
    )
    assert cloud._SESSIONS[key].port == 53682


def test_auth_url_honors_forwarded_https_origin(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, [[URL_LINE, TOKEN_LINE]])
    headers = {
        **s["a"]["headers"],
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "sermon.example.com",
    }
    r = client.get(
        "/api/cloud/auth-url",
        params={"provider": "drive", "name": "mydrive"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    key = cloud._session_key(s["a"]["id"], "mydrive")
    assert r.json()["url"] == (
        f"https://sermon.example.com/rclone-auth/{key}/auth?state=xpVTS69pf5uBqVw4Pf60VA"
    )


def test_auth_url_without_forwarded_headers_uses_request_base_url(
    client, scoped_setup, monkeypatch
):
    s = scoped_setup
    _stub_rclone(monkeypatch, [[URL_LINE, TOKEN_LINE]])
    r = client.get(
        "/api/cloud/auth-url",
        params={"provider": "drive", "name": "mydrive"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    key = cloud._session_key(s["a"]["id"], "mydrive")
    assert r.json()["url"] == (
        f"http://testserver/rclone-auth/{key}/auth?state=xpVTS69pf5uBqVw4Pf60VA"
    )


def test_auth_url_forwarded_host_beats_host_header(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, [[URL_LINE, TOKEN_LINE]])
    headers = {
        **s["a"]["headers"],
        "Host": "internal:8504",
        "X-FORWARDED-PROTO": "https",
        "X-FORWARDED-HOST": "public.example.com",
    }
    r = client.get(
        "/api/cloud/auth-url",
        params={"provider": "drive", "name": "mydrive"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    key = cloud._session_key(s["a"]["id"], "mydrive")
    assert r.json()["url"].startswith(f"https://public.example.com/rclone-auth/{key}/")


def test_proxy_forwards_request_to_session_port(client, monkeypatch):
    session = cloud._AuthorizeSession(_FakeProc([]))
    session.port = 53682
    cloud._SESSIONS["u:drive"] = session
    seen: dict = {}

    async def fake_forward(port, method, path, query, headers, body):
        seen.update(port=port, method=method, path=path, query=query, headers=headers, body=body)
        return httpx.Response(
            200,
            content=b"<html>consent</html>",
            headers={"content-type": "text/html"},
        )

    monkeypatch.setattr(cloud, "_forward", fake_forward)
    r = client.get("/rclone-auth/u:drive/auth?state=abc")
    assert r.status_code == 200, r.text
    assert r.text == "<html>consent</html>"
    assert r.headers["content-type"].startswith("text/html")
    assert seen["port"] == 53682
    assert seen["method"] == "GET"
    assert seen["path"] == "/auth"
    assert seen["query"] == "state=abc"
    assert "host" not in {k.lower() for k in seen["headers"]}


def test_proxy_forwards_real_get_with_query(client):
    seen: list[tuple[str, dict]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, dict(self.headers)))
            body = b"stub-ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        session = cloud._AuthorizeSession(_FakeProc([]))
        session.port = port
        cloud._SESSIONS["real:drive"] = session
        r = client.get("/rclone-auth/real:drive/auth?state=xyz")
        assert r.status_code == 200, r.text
        assert r.text == "stub-ok"
        assert seen[0][0] == "/auth?state=xyz"
        assert seen[0][1]["Host"] == f"127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def test_two_sessions_get_distinct_keys_and_ports(client, scoped_setup, monkeypatch):
    s = scoped_setup
    second = URL_LINE.replace("53682", "53683").replace("xpVTS69", "aaVTS69")
    _stub_rclone(monkeypatch, [[URL_LINE], [second]])
    first = client.get(
        "/api/cloud/auth-url",
        params={"provider": "drive", "name": "one"},
        headers=s["a"]["headers"],
    )
    other = client.get(
        "/api/cloud/auth-url",
        params={"provider": "drive", "name": "two"},
        headers=s["a"]["headers"],
    )
    key_one = cloud._session_key(s["a"]["id"], "one")
    key_two = cloud._session_key(s["a"]["id"], "two")
    assert key_one != key_two
    assert cloud._SESSIONS[key_one].port == 53682
    assert cloud._SESSIONS[key_two].port == 53683
    assert first.json()["url"] != other.json()["url"]


def test_unknown_session_key_returns_404(client):
    r = client.get("/rclone-auth/does-not-exist/auth?state=abc")
    assert r.status_code == 404


def test_token_collection_end_to_end_with_stubbed_rclone(scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, [[URL_LINE, TOKEN_LINE]])
    url = cloud._start_authorize(s["a"]["id"], "mydrive", "drive", "http://testserver/")
    key = cloud._session_key(s["a"]["id"], "mydrive")
    assert url.endswith(f"/rclone-auth/{key}/auth?state=xpVTS69pf5uBqVw4Pf60VA")
    assert cloud._SESSIONS[key].port == 53682
    token = cloud._collect_authorize_token(s["a"]["id"], "mydrive", timeout=1)
    assert json.loads(token)["access_token"] == "ya29.abc"
    assert key not in cloud._SESSIONS
