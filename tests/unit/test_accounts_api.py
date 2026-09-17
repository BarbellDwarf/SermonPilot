from __future__ import annotations

import secrets
import sqlite3

import pytest
from fastapi.testclient import TestClient

from server.api.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "accounts.db"
    monkeypatch.setenv("SERMONPILOT_DB", str(db_path))
    # minimal sermons schema so the read router can open the DB; auth runs FIRST
    from ui.database import SermonDatabase
    SermonDatabase(db_path=str(db_path)).init_database()
    monkeypatch.setenv("SERMONPILOT_ADMIN_USER", "test-admin")
    monkeypatch.setenv("SERMONPILOT_ADMIN_PASSWORD", secrets.token_urlsafe(24))
    with TestClient(create_app()) as client:
        yield client


def test_first_boot_and_auth_boundary(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["needs_bootstrap"] is True
    assert client.get("/api/sermons").status_code == 401
    assert client.get("/api/health").status_code == 200
    response = client.post("/api/auth/bootstrap")
    assert response.status_code == 201
    assert response.json()["role"] == "admin"
    assert "token" not in response.json()
    assert client.post("/api/auth/bootstrap").status_code == 400
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["needs_bootstrap"] is False
