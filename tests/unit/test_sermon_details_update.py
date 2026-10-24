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


def test_update_details_fills_previously_empty_fields(client, scoped_setup):
    s = scoped_setup
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO sermons (id, title, speaker, recorded_date, status, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("s-empty", "Title Needed", "", "", "draft", s["a"]["id"]),
    )
    conn.commit()
    conn.close()

    r = client.patch(
        "/api/sermons/s-empty",
        json={
            "title": "First Title",
            "speaker": "Speaker One",
            "series_title": "Series One",
            "recorded_date": "2026-10-01",
            "description": "A first description.",
        },
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "First Title"

    again = client.get("/api/sermons/s-empty", headers=s["a"]["headers"]).json()
    assert again["title"] == "First Title"
    assert again["speaker"] == "Speaker One"
    assert again["series"] == "Series One"
    assert again["date"] == "2026-10-01"
    assert again["description"] == "A first description."


def test_update_details_sets_every_empty_metadata_field(client, scoped_setup):
    s = scoped_setup
    r = client.patch(
        "/api/sermons/s-a",
        json={
            "subtitle": "A subtitle",
            "event_type": "Bible Study",
            "bible_text": "Sample 1:1",
            "scripture_reference": "Sample 1:1",
            "hashtags": "#one #two",
            "church_name": "Fixture Chapel",
            "notes": "Internal note",
        },
        headers=s["a"]["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bible_text"] == "Sample 1:1"
    assert body["scripture_reference"] == "Sample 1:1"

    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT subtitle, event_type, church_name, notes FROM sermons WHERE id = 's-a'"
    ).fetchone()
    content = conn.execute(
        "SELECT hashtags FROM sermon_content WHERE sermon_id = 's-a'"
    ).fetchone()
    conn.close()
    assert row == ("A subtitle", "Bible Study", "Fixture Chapel", "Internal note")
    assert content == ("#one #two",)


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
