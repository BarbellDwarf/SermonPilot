from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from server.api.app import create_app, resolve_spa_file

DIST = (Path(__file__).resolve().parents[2] / "web" / "dist").resolve()


def test_spa_serves_only_files_inside_dist(tmp_path):
    dist = (tmp_path / "dist").resolve()
    dist.mkdir()
    (dist / "index.html").write_text("shell", encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("js", encoding="utf-8")

    sibling = tmp_path / "dist-backup"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("secret", encoding="utf-8")

    assert resolve_spa_file(dist, "assets/app.js") == assets / "app.js"
    assert resolve_spa_file(dist, "index.html") == dist / "index.html"
    assert resolve_spa_file(dist, "") is None
    assert resolve_spa_file(dist, "missing.js") is None
    assert resolve_spa_file(dist, "../dist-backup/secret.txt") is None
    assert resolve_spa_file(dist, "/etc/passwd") is None


def test_spa_revalidates_the_shell_and_caches_hashed_assets():
    asset = next((DIST / "assets").iterdir())
    with TestClient(create_app()) as client:
        shell = client.get("/")
        assert shell.status_code == 200
        assert shell.headers["cache-control"] == "no-cache"

        hashed = client.get(f"/assets/{asset.name}")
        assert hashed.status_code == 200
        assert hashed.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_spa_answers_head_requests_without_a_body():
    asset = next((DIST / "assets").iterdir())
    with TestClient(create_app()) as client:
        shell = client.head("/")
        assert shell.status_code == 200
        assert shell.content == b""
        assert shell.headers["cache-control"] == "no-cache"

        hashed = client.head(f"/assets/{asset.name}")
        assert hashed.status_code == 200
        assert hashed.content == b""


def test_unmatched_api_path_is_json_404_not_the_spa(client, scoped_setup):
    headers = scoped_setup["admin_headers"]
    for path in (
        "/api/definitely-not-a-route",
        "/api/llm/providers",
        "/api/config",
        "/api/me/connections",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 404, path
        assert response.headers["content-type"].startswith("application/json")
        assert response.json() == {"detail": "not found"}

    head = client.head("/api/definitely-not-a-route", headers=headers)
    assert head.status_code == 404
    assert head.content == b""
    assert head.headers["content-type"].startswith("application/json")

    shell = client.get("/settings", headers=headers)
    assert shell.status_code == 200
    assert shell.headers["content-type"].startswith("text/html")
