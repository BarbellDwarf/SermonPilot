from __future__ import annotations

import configparser
import json
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

from server.api.accounts import get_db_path
from server.api.routers import cloud

AUTHORIZE_OUTPUT = (
    "2026/09/18 21:45:25 NOTICE: Please go to the following link: "
    "http://127.0.0.1:53682/auth?state=xpVTS69pf5uBqVw4Pf60VA\n"
    "2026/09/18 21:45:25 NOTICE: Log in and authorize rclone for access\n"
    "2026/09/18 21:45:25 NOTICE: Waiting for code...\n"
    "Paste the following into your remote machine --->\n"
    '{"access_token":"ya29.abc","token_type":"Bearer",'
    '"refresh_token":"1//xyz","expiry":"2026-01-01T00:00:00Z"}\n'
    "<---End paste\n"
)


@pytest.fixture(autouse=True)
def _cloud_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    cloud._SESSIONS.clear()
    cloud._SERVES.clear()
    yield
    cloud._SESSIONS.clear()
    cloud._SERVES.clear()


class _FakeProc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


class _FakePopen:
    def __init__(self, *args, **kwargs):
        self.pid = 4242

    def poll(self):
        return None


def _write_section(path: Path, name: str, values: dict) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    if path.is_file():
        parser.read(path, encoding="utf-8")
    parser[name] = {k: str(v) for k, v in values.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        parser.write(fh)


def _remove_section(path: Path, name: str) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    if path.is_file():
        parser.read(path, encoding="utf-8")
    if parser.has_section(name):
        parser.remove_section(name)
    with open(path, "w", encoding="utf-8") as fh:
        parser.write(fh)


def _fake_rclone(monkeypatch, cfg: Path, *, lsf_out: str = "", lsf_rc: int = 0) -> list:
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
            _write_section(cfg, name, values)
            return _FakeProc(0)
        if "lsf" in args:
            return _FakeProc(lsf_rc, lsf_out if lsf_rc == 0 else "", "lsf boom")
        if "config" in args and "delete" in args:
            _remove_section(cfg, args[args.index("delete") + 1])
            return _FakeProc(0)
        return _FakeProc(0)

    monkeypatch.setattr(cloud.shutil, "which", lambda _name: "/usr/bin/rclone")
    monkeypatch.setattr(cloud.subprocess, "run", fake)
    return calls


def test_providers_static_catalog(client, scoped_setup):
    r = client.get("/api/cloud/providers", headers=scoped_setup["a"]["headers"])
    assert r.status_code == 200
    assert [p["id"] for p in r.json()["items"]] == ["drive", "dropbox", "onedrive", "s3", "b2"]


def test_auth_url_emits_rclone_url(client, scoped_setup, monkeypatch):
    s = scoped_setup
    monkeypatch.setattr(
        cloud, "_start_authorize", lambda u, n, p: "http://127.0.0.1:53682/auth?state=abc"
    )
    r = client.get(
        "/api/cloud/auth-url",
        params={"provider": "drive", "name": "mydrive"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("http://127.0.0.1:53682/auth?")
    assert r.json()["name"] == "mydrive"

    keys = client.get(
        "/api/cloud/auth-url",
        params={"provider": "s3", "name": "b"},
        headers=s["a"]["headers"],
    )
    assert keys.status_code == 422


def test_authorize_parsers_read_rclone_output():
    assert (
        cloud.extract_authorize_url(AUTHORIZE_OUTPUT)
        == "http://127.0.0.1:53682/auth?state=xpVTS69pf5uBqVw4Pf60VA"
    )
    token = json.loads(cloud.extract_authorize_token(AUTHORIZE_OUTPUT))
    assert token["access_token"] == "ya29.abc"
    assert cloud.extract_authorize_token("no token here") == ""


def test_authorize_validates_and_stores_600(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg)
    monkeypatch.setattr(
        cloud,
        "_collect_authorize_token",
        lambda u, n, timeout=180: '{"access_token":"ya29.secret","refresh_token":"r"}',
    )
    r = client.post(
        "/api/cloud/authorize",
        json={"name": "mydrive", "provider": "drive"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 201, r.text
    assert "ya29.secret" not in r.text
    assert r.json() == {"name": "mydrive", "provider": "drive", "status": "configured"}
    assert cfg.is_file()
    assert oct(os.stat(cfg).st_mode & 0o777) == "0o600"
    listed = client.get("/api/cloud/remotes", headers=s["a"]["headers"])
    assert [i["name"] for i in listed.json()["items"]] == ["mydrive"]
    assert "ya29.secret" not in listed.text


def test_remotes_are_isolated_per_user(client, scoped_setup, monkeypatch):
    s = scoped_setup
    _fake_rclone(monkeypatch, cloud._config_path(s["a"]["id"]))
    monkeypatch.setattr(
        cloud, "_collect_authorize_token", lambda u, n, timeout=180: '{"access_token":"t"}'
    )
    created = client.post(
        "/api/cloud/authorize",
        json={"name": "mine", "provider": "drive"},
        headers=s["a"]["headers"],
    )
    assert created.status_code == 201, created.text
    assert client.get("/api/cloud/remotes", headers=s["b"]["headers"]).json()["total"] == 0
    assert client.delete("/api/cloud/remotes/mine", headers=s["b"]["headers"]).status_code == 404
    browse = client.post(
        "/api/cloud/remotes/mine/browse", json={"path": ""}, headers=s["b"]["headers"]
    )
    assert browse.status_code == 404
    assert client.get("/api/cloud/remotes", headers=s["a"]["headers"]).json()["total"] == 1


def test_key_remote_create_delete_and_secret_never_returned(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg)
    body = {
        "name": "backups",
        "provider": "s3",
        "keys": {"access_key_id": "AKIAEXAMPLE", "secret_access_key": "SUPERSECRET"},
    }
    r = client.post("/api/cloud/remotes", json=body, headers=s["a"]["headers"])
    assert r.status_code == 201, r.text
    assert "SUPERSECRET" not in r.text
    assert oct(os.stat(cfg).st_mode & 0o777) == "0o600"
    assert client.get("/api/cloud/remotes", headers=s["a"]["headers"]).json()["items"][0][
        "provider"
    ] == "s3"
    assert client.delete("/api/cloud/remotes/backups", headers=s["a"]["headers"]).status_code == 204
    assert client.get("/api/cloud/remotes", headers=s["a"]["headers"]).json()["total"] == 0


def test_failed_validation_rolls_back(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg, lsf_rc=1)
    body = {
        "name": "broken",
        "provider": "b2",
        "keys": {"account": "acct", "key": "key"},
    }
    r = client.post("/api/cloud/remotes", json=body, headers=s["a"]["headers"])
    assert r.status_code == 422
    assert client.get("/api/cloud/remotes", headers=s["a"]["headers"]).json()["total"] == 0


def test_browse_parses_lsf_listing(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg, lsf_out="1024;talk.mp3\n-1;sub/\n2048;more/talk2.mp3\n")
    seed = client.post(
        "/api/cloud/remotes",
        json={
            "name": "mine",
            "provider": "s3",
            "keys": {"access_key_id": "a", "secret_access_key": "b"},
        },
        headers=s["a"]["headers"],
    )
    assert seed.status_code == 201, seed.text
    r = client.post(
        "/api/cloud/remotes/mine/browse", json={"path": "talks"}, headers=s["a"]["headers"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "talks"
    items = r.json()["items"]
    assert items[0] == {"name": "talk.mp3", "path": "talk.mp3", "type": "file", "size": 1024}
    assert items[1]["type"] == "directory" and items[1]["size"] is None
    assert items[2]["name"] == "talk2.mp3" and items[2]["path"] == "more/talk2.mp3"


def test_missing_rclone_returns_503(client, scoped_setup, monkeypatch):
    s = scoped_setup
    monkeypatch.setattr(cloud.shutil, "which", lambda _name: None)
    auth = client.get(
        "/api/cloud/auth-url", params={"provider": "drive", "name": "x"}, headers=s["a"]["headers"]
    )
    assert auth.status_code == 503
    created = client.post(
        "/api/cloud/remotes",
        json={
            "name": "x",
            "provider": "s3",
            "keys": {"access_key_id": "a", "secret_access_key": "b"},
        },
        headers=s["a"]["headers"],
    )
    assert created.status_code == 503


def test_parse_remote_path_and_lsf_helpers():
    assert cloud.parse_remote_path("remote:mine:/talks/x.mp3") == ("mine", "talks/x.mp3")
    assert cloud.parse_remote_path("remote:mine") == ("mine", "")
    assert cloud.parse_remote_path("/local/x.mp3") is None
    assert cloud._parse_lsf("10;a.txt\n-1;dir/\n") == [
        {"name": "a.txt", "path": "a.txt", "type": "file", "size": 10},
        {"name": "dir", "path": "dir", "type": "directory", "size": None},
    ]


def test_serve_helper_returns_webdav_url(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _write_section(cfg, "mine", {"type": "s3"})
    monkeypatch.setattr(cloud.shutil, "which", lambda _name: "/usr/bin/rclone")
    monkeypatch.setattr(cloud.subprocess, "Popen", _FakePopen)

    url = cloud.resolve_remote_uri(s["a"]["id"], "remote:mine:/talks/a.mp3")
    assert url.startswith("http://127.0.0.1:")
    assert url.endswith("/talks/a.mp3")
    assert cloud.resolve_remote_uri(s["a"]["id"], "/local/a.mp3") is None
    assert cloud._load_serves(s["a"]["id"])
    with pytest.raises(HTTPException):
        cloud.resolve_remote_uri(s["a"]["id"], "remote:nope:/a.mp3")


def test_server_path_remote_uses_resolver(client, scoped_setup, monkeypatch):
    s = scoped_setup
    monkeypatch.setattr(
        cloud, "resolve_remote_uri", lambda uid, path: "http://127.0.0.1:9999/talks/a.mp3"
    )
    body = {
        "container_path": "remote:mine:/talks/a.mp3",
        "title": "Cloud Talk",
        "speaker": "Speaker A",
        "recorded_date": "2026-09-14",
        "event_type": "Sunday Service",
    }
    r = client.post("/api/sermons/server-path", json=body, headers=s["a"]["headers"])
    assert r.status_code == 201, r.text
    assert r.json()["filename"] == "a.mp3"
    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT parameters FROM background_jobs WHERE id = ?", (r.json()["job_id"],)
    ).fetchone()
    conn.close()
    params = json.loads(row[0])
    assert params["uploaded_file_path"] == "http://127.0.0.1:9999/talks/a.mp3"
