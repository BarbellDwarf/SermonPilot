from __future__ import annotations

import sqlite3

from server.api.accounts import get_db_path


def test_job_list_exposes_progress_for_running_rows(client, scoped_setup) -> None:
    conn = sqlite3.connect(get_db_path())
    conn.execute("UPDATE background_jobs SET progress = ? WHERE id = 'j-a'", (42.5,))
    conn.commit()
    conn.close()

    items = client.get("/api/jobs", headers=scoped_setup["a"]["headers"]).json()["items"]
    item = next(row for row in items if row["id"] == "j-a")
    assert item["progress"] == 42.5
