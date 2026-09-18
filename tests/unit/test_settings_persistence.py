from __future__ import annotations

import base64

from server.api.accounts import set_setting, writable_conn


def _seed_key(user_id: str, raw: str) -> None:
    enc = base64.b64encode(raw.encode()).decode()
    with writable_conn() as conn:
        set_setting(conn, user_id, "connections.llm", {"items": [{"id": "c1", "_apiKeyEnc": enc}]})


def test_settings_kv_roundtrip_and_isolation(client, scoped_setup):
    s = scoped_setup
    body = {"value": {"method": "deepfilternet", "gainDb": "0.5"}}
    r = client.put("/api/me/settings/audio", json=body, headers=s["a"]["headers"])
    assert r.status_code == 200
    got = client.get("/api/me/settings/audio", headers=s["a"]["headers"]).json()
    assert got["value"] == body["value"]
    assert client.get("/api/me/settings/audio", headers=s["b"]["headers"]).json()["value"] is None
    no_auth = client.put("/api/me/settings/audio", json=body)
    assert no_auth.status_code == 401


def test_me_patch_updates_profile(client, scoped_setup):
    s = scoped_setup
    r = client.patch(
        "/api/me",
        json={"display_name": "Operator A", "email": "a@example.com"},
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers=s["a"]["headers"]).json()
    assert me["display_name"] == "Operator A"
    assert me["email"] == "a@example.com"
    other = client.get("/api/auth/me", headers=s["b"]["headers"]).json()
    assert other["display_name"] == "user-b"


def test_backup_download_scoped_and_masked(client, scoped_setup):
    s = scoped_setup
    _seed_key(s["a"]["id"], "sk-hidden-9z")
    r = client.get("/api/me/backup", headers=s["a"]["headers"])
    assert r.status_code == 200
    assert "sk-hidden-9z" not in r.text
    data = r.json()
    assert data["backup_kind"] == "user-settings"
    assert data["account"]["id"] == s["a"]["id"]
    assert data["settings"]["connections.llm"]["items"][0]["masked_key"] == "********"


def test_admin_db_backup_masks_and_user_denied(client, scoped_setup):
    s = scoped_setup
    _seed_key(s["a"]["id"], "sk-hidden-9z")
    assert client.get("/api/me/backup", headers=s["b"]["headers"]).status_code == 200
    r = client.get("/api/admin/backup", headers=s["admin_headers"])
    assert r.status_code == 200
    assert "sk-hidden-9z" not in r.text
    data = r.json()
    assert data["backup_kind"] == "full-database"
    assert data["tables"]["users"] >= 1
    assert client.get("/api/admin/backup", headers=s["a"]["headers"]).status_code == 403


def test_restore_applies_user_settings(client, scoped_setup):
    s = scoped_setup
    payload = {"settings": {"audio": {"method": "clear-studio"}}}
    r = client.post("/api/me/restore", json=payload, headers=s["a"]["headers"])
    assert r.status_code == 200
    got = client.get("/api/me/settings/audio", headers=s["a"]["headers"]).json()
    assert got["value"] == {"method": "clear-studio"}
    assert client.get("/api/me/settings/audio", headers=s["b"]["headers"]).json()["value"] is None
    bad = client.post("/api/me/restore", json={"settings": "nope"}, headers=s["a"]["headers"])
    assert bad.status_code == 422


def test_restore_rejects_masked_secrets(client, scoped_setup):
    s = scoped_setup
    payload = {"settings": {"audio": {"key": "********"}}}
    r = client.post("/api/me/restore", json=payload, headers=s["a"]["headers"])
    assert r.status_code == 400
