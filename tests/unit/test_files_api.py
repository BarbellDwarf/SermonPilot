from __future__ import annotations

import base64

import pytest


@pytest.fixture(autouse=True)
def _allow_tmp_output_root(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIRECTORY", str(tmp_path))


def _seed_key(user_id: str, raw: str) -> None:
    from server.api.accounts import set_setting, writable_conn

    enc = base64.b64encode(raw.encode()).decode()
    with writable_conn() as conn:
        set_setting(conn, user_id, "connections.llm", {"items": [{"id": "c1", "_apiKeyEnc": enc}]})


def _seed_output_dir(user_id: str, path) -> None:
    from server.api.accounts import set_setting, writable_conn

    with writable_conn() as conn:
        set_setting(conn, user_id, "settings.general", {"output_dir": str(path)})


def test_me_files_lists_only_user_output_dir(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "processed"
    (outdir / "user-a-talk").mkdir(parents=True)
    (outdir / "shared.txt").write_bytes(b"root file")
    _seed_output_dir(s["a"]["id"], outdir)
    r = client.get("/api/me/files", headers=s["a"]["headers"])
    assert r.status_code == 200, r.text
    names = [f["name"] for f in r.json()["items"]]
    assert "user-a-talk" in names
    assert "shared.txt" in names


def test_output_dir_outside_allowed_roots_is_refused(client, scoped_setup, tmp_path):
    s = scoped_setup
    r = client.put(
        "/api/me/output-dir", json={"output_dir": "/etc"}, headers=s["a"]["headers"]
    )
    assert r.status_code == 422, r.text

    _seed_output_dir(s["a"]["id"], "/etc")
    files = client.get("/api/me/files", headers=s["a"]["headers"])
    assert files.status_code == 200
    assert files.json()["root"] != "/etc"
    dl = client.get(
        "/api/me/files/download", params={"path": "passwd"}, headers=s["a"]["headers"]
    )
    assert dl.status_code == 404


def test_file_download_path_traversal_blocked(client, scoped_setup, tmp_path):
    s = scoped_setup
    outdir = tmp_path / "processed2"
    (outdir / "u").mkdir(parents=True)
    (outdir / "u" / "keep.txt").write_bytes(b"hello")
    (tmp_path / "secret.txt").write_bytes(b"top secret")
    _seed_output_dir(s["a"]["id"], outdir)
    base = "/api/me/files/download?path="
    r = client.get(base + "u/keep.txt", headers=s["a"]["headers"])
    assert r.status_code == 200
    assert r.content == b"hello"
    assert client.get(base + "../secret.txt", headers=s["a"]["headers"]).status_code == 400
    assert client.get(base + "u/../../secret.txt", headers=s["a"]["headers"]).status_code == 400
    assert client.get(base + "u/nope.txt", headers=s["a"]["headers"]).status_code == 404


def test_file_download_rejects_sibling_directory_sharing_the_prefix(
    client, scoped_setup, tmp_path
):
    s = scoped_setup
    outdir = tmp_path / "processed3"
    (outdir / "u").mkdir(parents=True)
    (outdir / "u" / "keep.txt").write_bytes(b"hello")
    sibling = tmp_path / "processed3_vault"
    sibling.mkdir()
    (sibling / "secret.txt").write_bytes(b"top secret")
    _seed_output_dir(s["a"]["id"], outdir)

    base = "/api/me/files/download?path="
    r = client.get(base + "u/keep.txt", headers=s["a"]["headers"])
    assert r.status_code == 200
    assert r.content == b"hello"
    escaped = client.get(base + "../processed3_vault/secret.txt", headers=s["a"]["headers"])
    assert escaped.status_code == 400
    assert escaped.content != b"top secret"
