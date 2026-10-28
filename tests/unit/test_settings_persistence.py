from __future__ import annotations

import base64
import json

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
    assert data["tables"]["sermons"] >= 1
    assert data["data"]["sermons"]
    assert client.get("/api/admin/backup", headers=s["a"]["headers"]).status_code == 403


def _counts(db_path: str) -> dict[str, int]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("sermons", "edit_plans", "background_jobs", "users")
        }
    finally:
        conn.close()


def test_admin_backup_restore_round_trip(client, scoped_setup):
    s = scoped_setup
    from server.api.accounts import get_db_path

    with writable_conn() as conn:
        conn.execute(
            "INSERT INTO edit_plans (sermon_id, revision, proposed_start, proposed_end,"
            " status, remove_segments) VALUES (?, 1, 2.0, 30.0, 'pending_review', ?)",
            ("s-a", '[{"start_sec": 10.0, "end_sec": 12.0}]'),
        )

    backup = client.get("/api/admin/backup", headers=s["admin_headers"]).json()
    before = _counts(get_db_path())
    assert before["sermons"] >= 1 and before["edit_plans"] >= 1

    with writable_conn() as conn:
        conn.execute("DELETE FROM edit_plans WHERE sermon_id = ?", ("s-a",))
        conn.execute("DELETE FROM sermons WHERE id = ?", ("s-a",))
        conn.execute("DELETE FROM background_jobs WHERE id = ?", ("j-a",))
        conn.execute("UPDATE users SET display_name = 'mutated' WHERE id = ?", (s["a"]["id"],))

    assert _counts(get_db_path()) != before

    r = client.post(
        "/api/admin/restore",
        json={
            "backup_kind": backup["backup_kind"],
            "data": backup["data"],
            "user_settings": backup["user_settings"],
        },
        headers=s["admin_headers"],
    )
    assert r.status_code == 200, r.text
    assert _counts(get_db_path()) == before
    assert r.json()["restored"]["sermons"] == before["sermons"]

    from ui.database import SermonDatabase, SermonRepository

    repo = SermonRepository(SermonDatabase(db_path=get_db_path()))
    assert repo.get_sermon("s-a")["title"] == "Owned A"
    assert repo.get_current_edit_plan("s-a")["proposed_start"] == 2.0
    assert client.get("/api/jobs/j-a", headers=s["admin_headers"]).json()["id"] == "j-a"
    assert client.get("/api/auth/me", headers=s["admin_headers"]).json()["id"] == s["admin_id"]
    assert client.post(
        "/api/admin/restore",
        json={"backup_kind": "full-database", "data": backup["data"]},
        headers=s["a"]["headers"],
    ).status_code == 403


def test_admin_restore_rejects_masked_secrets(client, scoped_setup):
    s = scoped_setup
    _seed_key(s["a"]["id"], "sk-hidden-9z")
    backup = client.get("/api/admin/backup", headers=s["admin_headers"]).json()
    assert backup["user_settings"][s["a"]["id"]]["connections.llm"]["items"][0][
        "masked_key"
    ] == "********"

    for mask in ("********", "***"):
        masked = json.loads(json.dumps(backup))
        masked["user_settings"][s["a"]["id"]]["connections.llm"]["items"][0][
            "masked_key"
        ] = mask
        r = client.post(
            "/api/admin/restore",
            json={
                "backup_kind": "full-database",
                "data": masked["data"],
                "user_settings": masked["user_settings"],
            },
            headers=s["admin_headers"],
        )
        assert r.status_code == 400


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
