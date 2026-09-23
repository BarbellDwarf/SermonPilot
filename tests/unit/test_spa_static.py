from __future__ import annotations

from server.api.app import resolve_spa_file


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
