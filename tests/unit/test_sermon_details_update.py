from __future__ import annotations

import sqlite3

from server.api.accounts import get_db_path


def test_update_details_requires_auth_and_ownership(client, scoped_setup):
    s = scoped_setup
    assert client.patch("/api/sermons/s-a", json={"title": "New"}).status_code == 401
    foreign = client.patch(
        "/api/sermons/s-a", json={"title": "New"}, headers=s["b"]["headers"]
    )
    assert foreign.status_code == 404
    assert (
        client.patch(
            "/api/sermons/nope", json={"title": "New"}, headers=s["a"]["headers"]
        ).status_code
        == 404
    )


def test_update_details_persists_and_returns_the_row(client, scoped_setup):
    s = scoped_setup
    r = client.patch(
        "/api/sermons/s-a",
        json={
            "title": "Renamed Teaching",
            "speaker": "Speaker Z",
            "series_title": "Series Z",
            "recorded_date": "2026-09-20",
            "description": "A sharper description.",
        },
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Renamed Teaching"
    assert body["speaker"] == "Speaker Z"
    assert body["series"] == "Series Z"
    assert body["date"] == "2026-09-20"
    assert body["description"] == "A sharper description."

    again = client.get("/api/sermons/s-a", headers=s["a"]["headers"]).json()
    assert again["title"] == "Renamed Teaching"
    assert again["description"] == "A sharper description."

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT title, series_title, recorded_date FROM sermons WHERE id = 's-a'"
    ).fetchone()
    content = conn.execute(
        "SELECT description FROM sermon_content WHERE sermon_id = 's-a'"
    ).fetchone()
    conn.close()
    assert row == ("Renamed Teaching", "Series Z", "2026-09-20")
    assert content == ("A sharper description.",)


def test_update_details_rejects_an_empty_patch(client, scoped_setup):
    s = scoped_setup
    r = client.patch("/api/sermons/s-a", json={}, headers=s["a"]["headers"])
    assert r.status_code == 422


def test_update_details_blank_title_falls_back_to_untitled(client, scoped_setup):
    s = scoped_setup
    r = client.patch(
        "/api/sermons/s-a", json={"title": "   "}, headers=s["a"]["headers"]
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Untitled"
