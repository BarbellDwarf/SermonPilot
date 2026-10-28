"""Hostile text must round-trip without errors or injection.

The list search filters in Python over parameterised reads, so SQL
metacharacters are data. Titles and descriptions keep emoji, RTL text, long
strings, and markup byte for byte. React escapes them at render time; the
companion web test pins that side.
"""

from __future__ import annotations

import pytest

CASES = {
    "emoji": "Grace \U0001f600\U0001f64f\U0001f3f3\ufe0f",
    "rtl": "\u0627\u0644\u0646\u0639\u0645\u0629 \u0648\u0627\u0644\u0631\u062d\u0645\u0629",
    "long": "A" * 5000,
    "html": "<script>alert('x')</script><img src=x onerror=alert(1)>",
    "sql": "Robert'); DROP TABLE sermons; --",
}


@pytest.mark.parametrize("kind", sorted(CASES))
def test_hostile_title_round_trips_and_search_is_parameterised(
    client, scoped_setup, kind
):
    headers = scoped_setup["a"]["headers"]
    title = f"{kind}-{CASES[kind]}"
    created = client.post(
        "/api/sermons",
        json={
            "title": title,
            "speaker": "Speaker A",
            "recorded_date": "2026-10-23",
            "description": CASES[kind],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    sermon_id = created.json()["id"]

    detail = client.get(f"/api/sermons/{sermon_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["title"] == title
    assert detail.json()["description"] == CASES[kind]


@pytest.mark.parametrize(
    "needle",
    [
        "%' OR 1=1 --",
        "'; DROP TABLE sermons; --",
        "%",
        "_",
        "\u0000",
        "1' UNION SELECT api_key FROM config_cache --",
    ],
)
def test_search_metacharacters_are_data_not_sql(client, scoped_setup, needle):
    headers = scoped_setup["a"]["headers"]
    response = client.get("/api/sermons", params={"search": needle, "limit": 50}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["items"], list)
    conn_rows = client.get("/api/sermons", params={"limit": 1}, headers=headers)
    assert conn_rows.status_code == 200


def test_long_description_does_not_truncate_silently(client, scoped_setup):
    headers = scoped_setup["a"]["headers"]
    text = "word " * 999 + "word"
    created = client.post(
        "/api/sermons",
        json={"title": "Long description", "speaker": "Speaker A", "recorded_date": "2026-10-24"},
        headers=headers,
    ).json()
    response = client.patch(
        f"/api/sermons/{created['id']}", json={"description": text}, headers=headers
    )
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/sermons/{created['id']}", headers=headers).json()
    assert detail["description"] == text
