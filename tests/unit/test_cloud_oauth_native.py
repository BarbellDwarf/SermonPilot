from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from server.api.routers import cloud

TOKEN_RESPONSE = {
    "access_token": "ya29.access",
    "refresh_token": "1//refresh",
    "token_type": "Bearer",
    "expires_in": 3600,
}


@pytest.fixture(autouse=True)
def _cloud_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    monkeypatch.setenv("SERMONPILOT_OAUTH_STATE_SECRET", "test-state-secret")
    cloud._CONSUMED_STATES.clear()
    cloud._STATE_SECRET = None
    yield
    cloud._CONSUMED_STATES.clear()
    cloud._STATE_SECRET = None


class _FakeProc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


def _fake_rclone(monkeypatch, cfg: Path) -> list:
    calls: list = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
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
            return _FakeProc(0)
        return _FakeProc(0)

    monkeypatch.setattr(cloud.shutil, "which", lambda _name: "/usr/bin/rclone")
    monkeypatch.setattr(cloud.subprocess, "run", fake)
    return calls


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data=None, **kwargs):
        _FakeAsyncClient.calls.append(("post", url, data))
        return _FakeResponse(200, TOKEN_RESPONSE)

    async def request(self, method, url, **kwargs):
        _FakeAsyncClient.calls.append((method, url, kwargs))
        return _FakeResponse(200, {"user": {"displayName": "Tester"}})


def _store_app(client, scoped_setup, provider="drive"):
    body = {
        "provider": provider,
        "client_id": "cid.apps.googleusercontent.com",
        "client_secret": "shh",
    }
    return client.put("/api/cloud/oauth-app", json=body, headers=scoped_setup["admin_headers"])


def _start(client, scoped_setup, provider="drive", name="mydrive"):
    return client.get(
        "/api/cloud/oauth/start",
        params={"provider": provider, "name": name},
        headers=scoped_setup["a"]["headers"],
    )


def test_oauth_app_admin_only_and_secret_hidden(client, scoped_setup):
    s = scoped_setup
    r = client.put(
        "/api/cloud/oauth-app",
        json={"provider": "drive", "client_id": "cid", "client_secret": "topsecret"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 403
    stored = _store_app(client, s)
    assert stored.status_code == 200, stored.text
    assert "topsecret" not in stored.text
    status = client.get("/api/cloud/oauth-app", headers=s["a"]["headers"])
    assert status.status_code == 200
    assert status.json()["providers"]["drive"]["has_credentials"] is True
    assert status.json()["providers"]["dropbox"]["has_credentials"] is False
    assert "topsecret" not in status.text
    assert "client_id" not in status.text
    app_file = cloud._rclone_dir() / "oauth_apps.json"
    assert oct(os.stat(app_file).st_mode & 0o777) == "0o600"
    empty = client.put(
        "/api/cloud/oauth-app",
        json={"provider": "drive", "client_id": "cid", "client_secret": " "},
        headers=s["admin_headers"],
    )
    assert empty.status_code == 422


def test_oauth_start_builds_provider_url(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _store_app(client, s)
    r = _start(client, s)
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    parsed = urlsplit(url)
    assert parsed.netloc == "accounts.google.com"
    params = parse_qs(parsed.query)
    assert params["client_id"] == ["cid.apps.googleusercontent.com"]
    assert params["redirect_uri"] == ["http://testserver/api/cloud/oauth/callback"]
    assert params["scope"] == ["https://www.googleapis.com/auth/drive"]
    assert params["access_type"] == ["offline"]
    assert params["response_type"] == ["code"]
    assert params["state"][0]

    hosted = (("dropbox", "www.dropbox.com"), ("onedrive", "login.microsoftonline.com"))
    for provider, host in hosted:
        _store_app(client, s, provider)
        other = _start(client, s, provider, "r-" + provider)
        assert other.status_code == 200, other.text
        assert urlsplit(other.json()["url"]).netloc == host

    keys = client.get(
        "/api/cloud/oauth/start",
        params={"provider": "s3", "name": "x"},
        headers=s["a"]["headers"],
    )
    assert keys.status_code == 422


def test_oauth_start_requires_admin_credentials(client, scoped_setup):
    r = _start(client, scoped_setup)
    assert r.status_code == 422
    assert "admin" in r.json()["detail"]


def test_oauth_callback_rejects_bad_state(client, scoped_setup):
    bad = client.get("/api/cloud/oauth/callback", params={"code": "c", "state": "junk"})
    assert bad.status_code == 400
    s = scoped_setup
    _store_app(client, s)
    started = _start(client, s).json()
    state = parse_qs(urlsplit(started["url"]).query)["state"][0]
    tampered = state[:-2] + ("aa" if state[-2:] != "aa" else "bb")
    assert client.get(
        "/api/cloud/oauth/callback", params={"code": "c", "state": tampered}
    ).status_code == 400


def test_oauth_callback_happy_path_stores_remote(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _store_app(client, s)
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg)
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(cloud.httpx, "AsyncClient", _FakeAsyncClient)
    started = _start(client, s).json()
    state = parse_qs(urlsplit(started["url"]).query)["state"][0]

    r = client.get(
        "/api/cloud/oauth/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert "/settings?cloud=connected&name=mydrive" in r.headers["location"]

    token_call = next(c for c in _FakeAsyncClient.calls if c[0] == "post")
    assert token_call[2]["code"] == "auth-code"
    assert token_call[2]["redirect_uri"] == "http://testserver/api/cloud/oauth/callback"
    assert any("drive/v3/about" in c[1] for c in _FakeAsyncClient.calls if c[0] == "GET")

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(cfg, encoding="utf-8")
    assert parser["mydrive"]["type"] == "drive"
    assert parser["mydrive"]["client_id"] == "cid.apps.googleusercontent.com"
    assert parser["mydrive"]["client_secret"] == "shh"
    token = json.loads(parser["mydrive"]["token"])
    assert token["access_token"] == "ya29.access"
    assert token["refresh_token"] == "1//refresh"
    assert token["expiry"].endswith("Z")

    listed = client.get("/api/cloud/remotes", headers=s["a"]["headers"])
    assert listed.json()["items"][0]["name"] == "mydrive"
    assert "ya29.access" not in listed.text
    assert client.get("/api/cloud/remotes", headers=s["b"]["headers"]).json()["total"] == 0

    reused = client.get(
        "/api/cloud/oauth/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert reused.status_code == 400


def test_oauth_callback_provider_error_page(client):
    r = client.get("/api/cloud/oauth/callback", params={"error": "access_denied"})
    assert r.status_code == 200
    assert "Authorization failed" in r.text
    xss = client.get("/api/cloud/oauth/callback", params={"error": "<script>alert(1)</script>"})
    assert "<script>" not in xss.text
    assert "&lt;script&gt;" in xss.text
