from __future__ import annotations

import sqlite3

from server.api.accounts import get_db_path


def _insert_sermons(user_id: str, rows: list[tuple[str, str, str, str]]) -> None:
    conn = sqlite3.connect(get_db_path())
    for sid, speaker, series, event in rows:
        conn.execute(
            "INSERT INTO sermons (id, title, speaker, series_title, event_type,"
            " recorded_date, status, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, f"T {sid}", speaker, series, event, "2026-01-01", "processed", user_id),
        )
    conn.commit()
    conn.close()


def test_facets_distinct_ordered_and_scoped(client, scoped_setup):
    s = scoped_setup
    _insert_sermons(
        s["a"]["id"],
        [
            ("f-a1", "Beta", "Series A", "Sunday Service"),
            ("f-a2", "Beta", "Series A", "Sunday Service"),
            ("f-a3", "Alpha", "Series B", "Bible Study"),
        ],
    )

    r = client.get("/api/library/facets", headers=s["a"]["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["speakers"] == [
        {"name": "Beta", "count": 2},
        {"name": "Alpha", "count": 1},
        {"name": "Speaker A", "count": 1},
    ]
    assert body["series"][0] == {"name": "Series A", "count": 2}
    assert body["event_types"][0] == {"name": "Sunday Service", "count": 2}
    # user_b must not see user_a's history
    other = client.get("/api/library/facets", headers=s["b"]["headers"]).json()
    assert all(item["name"] != "Beta" for item in other["speakers"])
    assert client.get("/api/library/facets").status_code == 401


def test_facets_empty_for_fresh_user(client, scoped_setup):
    s = scoped_setup
    created = client.post(
        "/api/admin/users",
        json={
            "username": "fresh",
            "display_name": "fresh",
            "password": "pw-fresh",
            "role": "user",
        },
        headers=s["admin_headers"],
    ).json()
    token = client.post(
        "/api/auth/login", json={"username": "fresh", "password": "pw-fresh"}
    ).json()["token"]
    assert created["id"]
    body = client.get(
        "/api/library/facets", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert body == {"speakers": [], "series": [], "event_types": []}


def test_facets_capped_at_200(client, scoped_setup):
    s = scoped_setup
    _insert_sermons(
        s["a"]["id"],
        [(f"cap-{i}", f"Speaker {i:04d}", "", "") for i in range(205)],
    )
    r = client.get("/api/library/facets", headers=s["a"]["headers"])
    assert r.status_code == 200
    assert len(r.json()["speakers"]) == 200


def test_new_sermon_wires_facets_typeahead():
    from pathlib import Path

    web = Path(__file__).resolve().parents[2] / "web" / "src"
    client_src = (web / "api" / "client.ts").read_text(encoding="utf-8")
    page = (web / "pages" / "NewSermon.tsx").read_text(encoding="utf-8")
    combobox = (web / "components" / "Combobox.tsx").read_text(encoding="utf-8")
    assert "/api/library/facets" in client_src
    assert "libraryApi.facets()" in page
    assert "facetSpeakerOptions" in page
    assert "facetSeriesOptions" in page
    assert page.count("<Combobox") == 2
    assert 'id="ns-speaker"' in page
    assert 'id="ns-series"' in page
    assert 'role="combobox"' in combobox
    assert 'role="listbox"' in combobox
    assert 'role="option"' in combobox
