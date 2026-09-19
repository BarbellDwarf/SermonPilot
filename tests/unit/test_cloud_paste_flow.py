from __future__ import annotations

import configparser
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
STATE = "xpVTS69pf5uBqVw4Pf60VA"
SCOPE = "drive.readonly"
REDIRECT = f"http://127.0.0.1:53682/?code=AUTHCODE&state={STATE}&scope={SCOPE}"


class _FakeProc:
    def __init__(self, lines: list[str]) -> None:
        self.stdout = list(lines)
        self.pid = 4242
        self.killed = False

    def poll(self) -> int | None:
        return 0 if self.killed else None

    def kill(self) -> None:
        self.killed = True


class _FakeRun:
    def __init__(self, rc: int = 0, out: str = "", err: str = "") -> None:
        self.returncode = rc
        self.stdout = out
        self.stderr = err


@pytest.fixture(autouse=True)
def _cloud_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    cloud._SESSIONS.clear()
    yield
    cloud._SESSIONS.clear()


def _stub_rclone(monkeypatch, cfg, lines: list[str]) -> None:
    def fake(cmd, **kwargs):
        args = cmd[3:]
        if "config" in args and "create" in args:
            idx = args.index("create")
            name, provider = args[idx + 1], args[idx + 2]
            values = {"type": provider}
            for token in args[idx + 3:]:
                key, _, value = token.partition("=")
                values[key] = value
            parser = configparser.ConfigParser(interpolation=None)
            if cfg.is_file():
                parser.read(cfg, encoding="utf-8")
            parser[name] = values
            cfg.parent.mkdir(parents=True, exist_ok=True)
            with open(cfg, "w", encoding="utf-8") as fh:
                parser.write(fh)
            return _FakeRun(0)
        if "lsf" in args:
            return _FakeRun(0, "ok\n")
        return _FakeRun(0)

    monkeypatch.setattr(cloud.shutil, "which", lambda _name: "/usr/bin/rclone")
    monkeypatch.setattr(cloud.subprocess, "run", fake)
    monkeypatch.setattr(cloud.subprocess, "Popen", lambda *a, **k: _FakeProc(lines))


class _Listener:
    def __init__(self) -> None:
        self.seen: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.seen.append(self.path)
                body = b"authorized"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start(client, scoped_setup, name: str = "mydrive") -> dict:
    r = client.get(
        "/api/cloud/auth-url",
        params={"provider": "drive", "name": name},
        headers=scoped_setup["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    return r.json()


def _paste(client, scoped_setup, redirect_url: str, name: str = "mydrive"):
    return client.post(
        "/api/cloud/authorize/paste",
        json={"name": name, "provider": "drive", "redirect_url": redirect_url},
        headers=scoped_setup["a"]["headers"],
    )


def test_auth_url_returns_paste_instructions_and_session_key(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, cloud._config_path(s["a"]["id"]), [URL_LINE, TOKEN_LINE])
    body = _start(client, s)
    key = cloud._session_key(s["a"]["id"], "mydrive")
    assert body["session_key"] == key
    assert body["provider"] == "drive"
    assert body["name"] == "mydrive"
    assert "address bar" in body["instructions"]
    assert cloud._SESSIONS[key].state == STATE


def test_paste_happy_path_forwards_and_stores(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _stub_rclone(monkeypatch, cfg, [URL_LINE, TOKEN_LINE])
    listener = _Listener()
    try:
        _start(client, s)
        key = cloud._session_key(s["a"]["id"], "mydrive")
        cloud._SESSIONS[key].port = listener.port
        r = _paste(client, s, REDIRECT)
        assert r.status_code == 201, r.text
        assert r.json() == {"name": "mydrive", "provider": "drive", "status": "configured"}
        assert "code=AUTHCODE" in listener.seen[0]
        assert f"scope={SCOPE}" in listener.seen[0]
        assert "ya29.abc" not in r.text
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(cfg, encoding="utf-8")
        assert parser["mydrive"]["type"] == "drive"
        assert "ya29.abc" in parser["mydrive"]["token"]
        listed = client.get("/api/cloud/remotes", headers=s["a"]["headers"])
        assert [i["name"] for i in listed.json()["items"]] == ["mydrive"]
    finally:
        listener.close()


def test_paste_wrong_session_name_returns_404(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, cloud._config_path(s["a"]["id"]), [URL_LINE, TOKEN_LINE])
    _start(client, s)
    r = _paste(client, s, REDIRECT, name="ghost")
    assert r.status_code == 404


def test_paste_code_missing_returns_422(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, cloud._config_path(s["a"]["id"]), [URL_LINE, TOKEN_LINE])
    _start(client, s)
    r = _paste(client, s, f"http://127.0.0.1:53682/?state={STATE}")
    assert r.status_code == 422
    assert "code" in r.json()["detail"]


def test_paste_forwarding_failure_returns_422(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, cloud._config_path(s["a"]["id"]), [URL_LINE, TOKEN_LINE])
    _start(client, s)
    key = cloud._session_key(s["a"]["id"], "mydrive")
    cloud._SESSIONS[key].port = _closed_port()
    r = _paste(client, s, REDIRECT)
    assert r.status_code == 422
    assert "rclone listener" in r.json()["detail"]
    assert key not in cloud._SESSIONS


def test_paste_state_mismatch_rejected_and_session_discarded(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, cloud._config_path(s["a"]["id"]), [URL_LINE, TOKEN_LINE])
    _start(client, s)
    key = cloud._session_key(s["a"]["id"], "mydrive")
    r = _paste(client, s, "http://127.0.0.1:53682/?code=AUTHCODE&state=someone-elses")
    assert r.status_code == 422
    assert "state" in r.json()["detail"]
    assert key not in cloud._SESSIONS


def test_paste_code_only_accepted_when_session_young(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _stub_rclone(monkeypatch, cfg, [URL_LINE, TOKEN_LINE])
    listener = _Listener()
    try:
        _start(client, s)
        key = cloud._session_key(s["a"]["id"], "mydrive")
        cloud._SESSIONS[key].port = listener.port
        r = _paste(client, s, "http://127.0.0.1:53682/?code=AUTHCODE")
        assert r.status_code == 201, r.text
    finally:
        listener.close()


def test_paste_code_only_rejected_when_session_old(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, cloud._config_path(s["a"]["id"]), [URL_LINE, TOKEN_LINE])
    _start(client, s)
    key = cloud._session_key(s["a"]["id"], "mydrive")
    cloud._SESSIONS[key].started = time.time() - (cloud._PASTE_STATE_GRACE + 60)
    r = _paste(client, s, "http://127.0.0.1:53682/?code=AUTHCODE")
    assert r.status_code == 422
    assert key not in cloud._SESSIONS


def test_paste_is_per_user(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _stub_rclone(monkeypatch, cloud._config_path(s["a"]["id"]), [URL_LINE, TOKEN_LINE])
    _start(client, s)
    r = client.post(
        "/api/cloud/authorize/paste",
        json={"name": "mydrive", "provider": "drive", "redirect_url": REDIRECT},
        headers=s["b"]["headers"],
    )
    assert r.status_code == 404


def test_parse_redirect_helpers():
    assert cloud._parse_redirect(REDIRECT) == ("AUTHCODE", STATE, SCOPE)
    assert cloud._parse_redirect(f"code=AUTHCODE&state={STATE}") == ("AUTHCODE", STATE, "")
    assert cloud._parse_redirect("AUTHCODE") == ("AUTHCODE", "", "")
    assert cloud._parse_redirect("") == ("", "", "")
