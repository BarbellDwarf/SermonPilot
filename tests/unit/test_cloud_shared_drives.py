from __future__ import annotations

import configparser
from pathlib import Path

import pytest

from server.api.routers import cloud

DRIVES_JSON = (
    '[{"id":"0ABCdef","name":"Church Media"},{"id":"0GHIjkl","name":"Archives"}]'
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


def _write_section(path: Path, name: str, values: dict) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    if path.is_file():
        parser.read(path, encoding="utf-8")
    parser[name] = {k: str(v) for k, v in values.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        parser.write(fh)


def _read_option(path: Path, name: str, option: str) -> str:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    if parser.has_section(name) and parser.has_option(name, option):
        return parser.get(name, option)
    return ""


def _fake_rclone(
    monkeypatch, cfg: Path, *, lsf_rc=0, lsf_out="ok\n", drives_out=DRIVES_JSON
) -> list:
    calls: list = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
        args = cmd[3:]
        if "backend" in args and "drives" in args:
            return _FakeProc(0, drives_out)
        if "config" in args and "update" in args:
            idx = args.index("update")
            name, option, value = args[idx + 1], args[idx + 2], args[idx + 3]
            parser = configparser.ConfigParser(interpolation=None)
            if cfg.is_file():
                parser.read(cfg, encoding="utf-8")
            if not parser.has_section(name):
                parser.add_section(name)
            parser[name][option] = value
            with open(cfg, "w", encoding="utf-8") as fh:
                parser.write(fh)
            return _FakeProc(0)
        if "lsf" in args:
            return _FakeProc(lsf_rc, lsf_out if lsf_rc == 0 else "", "lsf boom")
        return _FakeProc(0)

    monkeypatch.setattr(cloud.shutil, "which", lambda _name: "/usr/bin/rclone")
    monkeypatch.setattr(cloud.subprocess, "run", fake)
    return calls


def _seed_drive(cfg: Path, name: str = "mydrive", team_drive: str | None = None) -> None:
    values = {"type": "drive", "token": "{}"}
    if team_drive is not None:
        values["team_drive"] = team_drive
    _write_section(cfg, name, values)


def test_shared_drives_listing_parses(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg)
    _seed_drive(cfg)
    r = client.get("/api/cloud/remotes/mydrive/shared-drives", headers=s["a"]["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["items"] == [
        {"id": "0ABCdef", "name": "Church Media"},
        {"id": "0GHIjkl", "name": "Archives"},
    ]


def test_shared_drives_bad_json_is_422(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg, drives_out="not json")
    _seed_drive(cfg)
    r = client.get("/api/cloud/remotes/mydrive/shared-drives", headers=s["a"]["headers"])
    assert r.status_code == 422


def test_attach_updates_config_and_validates(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg)
    _seed_drive(cfg)
    r = client.post(
        "/api/cloud/remotes/mydrive/attach-shared-drive",
        json={"drive_id": "0ABCdef"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "name": "mydrive", "team_drive": "0ABCdef"}
    assert _read_option(cfg, "mydrive", "team_drive") == "0ABCdef"
    listed = client.get("/api/cloud/remotes", headers=s["a"]["headers"]).json()["items"]
    assert listed[0]["team_drive"] == "0ABCdef"


def test_attach_rolls_back_on_validation_failure(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg, lsf_rc=1)
    _seed_drive(cfg, team_drive="0KEEP")
    r = client.post(
        "/api/cloud/remotes/mydrive/attach-shared-drive",
        json={"drive_id": "0BAD"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 422
    assert _read_option(cfg, "mydrive", "team_drive") == "0KEEP"


def test_detach_clears_team_drive(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg)
    _seed_drive(cfg, team_drive="0ABCdef")
    r = client.post("/api/cloud/remotes/mydrive/detach-shared-drive", headers=s["a"]["headers"])
    assert r.status_code == 200, r.text
    assert _read_option(cfg, "mydrive", "team_drive") == ""


def test_browse_with_drive_id_uses_alias(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    calls = _fake_rclone(monkeypatch, cfg, lsf_out="talk.mp3;1024;2026-09-20 20:47:00\n")
    _seed_drive(cfg)
    r = client.post(
        "/api/cloud/remotes/mydrive/browse",
        params={"drive_id": "0ABCdef"},
        json={"path": "talks"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["name"] == "talk.mp3"
    lsf_targets = [c[c.index("lsf") + 1] for c in calls if "lsf" in c]
    assert lsf_targets == ["mydrive,team_drive=0ABCdef:talks"]

    client.post(
        "/api/cloud/remotes/mydrive/browse",
        json={"path": "talks"},
        headers=s["a"]["headers"],
    )
    lsf_targets = [c[c.index("lsf") + 1] for c in calls if "lsf" in c]
    assert lsf_targets[-1] == "mydrive:talks"


def test_non_drive_remote_is_422(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg)
    _write_section(cfg, "backups", {"type": "s3"})
    listed = client.get("/api/cloud/remotes/backups/shared-drives", headers=s["a"]["headers"])
    assert listed.status_code == 422
    attached = client.post(
        "/api/cloud/remotes/backups/attach-shared-drive",
        json={"drive_id": "0ABC"},
        headers=s["a"]["headers"],
    )
    assert attached.status_code == 422
    detached = client.post(
        "/api/cloud/remotes/backups/detach-shared-drive", headers=s["a"]["headers"]
    )
    assert detached.status_code == 422


def test_shared_drives_missing_remote_is_404(client, scoped_setup, monkeypatch):
    s = scoped_setup
    cfg = cloud._config_path(s["a"]["id"])
    _fake_rclone(monkeypatch, cfg)
    r = client.get("/api/cloud/remotes/nope/shared-drives", headers=s["a"]["headers"])
    assert r.status_code == 404
