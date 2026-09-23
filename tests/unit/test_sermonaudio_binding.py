"""A job publishes only with its owner's SermonAudio account.

Two users with different accounts must resolve to their own credentials; a
user with no account must be refused rather than fall back to another user's;
and the bootstrap fallback must apply only when no account exists anywhere.
No test here may observe a secret in a log line or a resolved config blob.
"""

from __future__ import annotations

import base64
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from ui import sermonaudio_accounts as sa
from ui.job_executors import (
    execute_sermon_processing_job,
    resolve_job_config,
    sermonaudio_refusal,
)
from ui.job_queue import Job, JobStatus, JobType

AUDIO_FILE = str(Path(__file__).resolve())

FORM_DATA = {
    "speaker_name": "Test Speaker",
    "recorded_date": "2024-01-01",
    "event_type": "Sunday Service",
}

SUCCESS_RESULT = {"success": True, "sermon_id": "s-1", "transcript": "body"}


def _enc(key: str) -> str:
    return base64.b64encode(key.encode()).decode()


def _seed(path: Path, user_id: str, items: list[dict], default_id: str | None = None) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_settings ("
        " user_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT,"
        " PRIMARY KEY (user_id, key))"
    )
    conn.execute(
        "INSERT OR REPLACE INTO user_settings (user_id, key, value) VALUES (?, ?, ?)",
        (user_id, sa.SETTING_KEY, json.dumps({"items": items, "default_id": default_id})),
    )
    conn.commit()
    conn.close()


def _account(account_id: str, name: str, key: str, broadcaster: str) -> dict:
    return {
        "id": account_id,
        "name": name,
        "broadcasterId": broadcaster,
        "_apiKeyEnc": _enc(key),
    }


def _job(user_id: str | None, **extra: Any) -> Job:
    params: dict[str, Any] = {"config": {}, **extra}
    if user_id is not None:
        params["user_id"] = user_id
    return Job(
        id="job-sa-binding",
        type=JobType.SERMON_PROCESSING,
        title="Binding",
        description="Binding",
        status=JobStatus.RUNNING,
        progress=0.0,
        created_at=datetime.now(),
        parameters=params,
    )


def _point_at(monkeypatch: pytest.MonkeyPatch, db: Path) -> None:
    monkeypatch.setenv("SERMONPILOT_DB", str(db))
    monkeypatch.setenv("DATABASE_URL", str(db))


def _global_config() -> dict[str, Any]:
    return {"api_key": "global-key", "broadcaster_id": "global-broadcaster"}


def test_job_resolves_to_its_owners_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")
    _seed(db, "u-b", [_account("sa-b", "Beta", "key-beta-2222", "beta")], "sa-b")
    _point_at(monkeypatch, db)
    monkeypatch.setattr("ui.config_utils.resolve_config", lambda db=None: _global_config())

    a = resolve_job_config(_job("u-a"))
    b = resolve_job_config(_job("u-b"))

    assert (a["api_key"], a["broadcaster_id"]) == ("key-alpha-1111", "alpha")
    assert a["sermonaudio_connection"]["account_name"] == "Alpha"
    assert (b["api_key"], b["broadcaster_id"]) == ("key-beta-2222", "beta")
    assert b["sermonaudio_connection"]["account_name"] == "Beta"


def test_job_without_account_never_borrows_another_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")
    _point_at(monkeypatch, db)
    monkeypatch.setattr("ui.config_utils.resolve_config", lambda db=None: _global_config())

    resolved = resolve_job_config(_job("u-b"))

    assert resolved["api_key"] == ""
    assert resolved["broadcaster_id"] == ""
    assert resolved["sermonaudio_connection"]["configured"] is False
    assert "key-alpha-1111" not in json.dumps(resolved)


def test_job_without_owner_keeps_the_global_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")
    _point_at(monkeypatch, db)
    monkeypatch.setattr("ui.config_utils.resolve_config", lambda db=None: _global_config())

    resolved = resolve_job_config(_job(None))

    assert resolved["api_key"] == "global-key"
    assert resolved["broadcaster_id"] == "global-broadcaster"


def test_bootstrap_source_reported_when_no_account_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [], None)
    _point_at(monkeypatch, db)
    fallback = sa.SermonAudioConnection(
        api_key="bootstrap-key", broadcaster_id="bootstrap", source="SERMONAUDIO_API_KEY"
    )
    monkeypatch.setattr("ui.sermonaudio_accounts.bootstrap_connection", lambda: fallback)
    monkeypatch.setattr("ui.config_utils.resolve_config", lambda db=None: _global_config())

    resolved = resolve_job_config(_job("u-new"))

    assert resolved["api_key"] == "bootstrap-key"
    assert resolved["sermonaudio_connection"]["configured"] is True
    assert resolved["sermonaudio_connection"]["source"] == "SERMONAUDIO_API_KEY"


def test_publish_executor_refuses_without_an_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")
    _point_at(monkeypatch, db)
    process = Mock(side_effect=AssertionError("publish must not run"))
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)

    job = _job("u-b", form_data=FORM_DATA, uploaded_file_path=AUDIO_FILE)
    result = execute_sermon_processing_job(job)

    assert result.success is False
    assert result.error == sa.CONNECT_ACCOUNT_MESSAGE
    process.assert_not_called()


def test_publish_executor_uses_the_owners_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")
    _seed(db, "u-b", [_account("sa-b", "Beta", "key-beta-2222", "beta")], "sa-b")
    _point_at(monkeypatch, db)
    monkeypatch.setattr("ui.config_utils.resolve_config", lambda db=None: _global_config())
    process = Mock(return_value=SUCCESS_RESULT)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)

    job = _job("u-b", form_data=FORM_DATA, uploaded_file_path=AUDIO_FILE)
    result = execute_sermon_processing_job(job)

    assert result.success is True
    passed = process.call_args.kwargs["config"]
    assert passed["api_key"] == "key-beta-2222"
    assert passed["broadcaster_id"] == "beta"


def test_no_secret_leaks_into_logs_or_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "sa-live-secret-7890", "alpha")], "sa-a")
    _point_at(monkeypatch, db)
    monkeypatch.setattr("ui.config_utils.resolve_config", lambda db=None: _global_config())
    process = Mock(return_value=SUCCESS_RESULT)
    monkeypatch.setattr("sermon_updater.process_new_sermon", process)

    with caplog.at_level(logging.DEBUG):
        job = _job("u-a", form_data=FORM_DATA, uploaded_file_path=AUDIO_FILE)
        execute_sermon_processing_job(job)

    assert "sa-live-secret-7890" not in caplog.text
    passed = process.call_args.kwargs["config"]
    assert passed["api_key"] == "sa-live-secret-7890"
    assert "sa-live-secret-7890" not in json.dumps(job.parameters)
    assert "sa-live-secret-7890" not in json.dumps(sermonaudio_refusal(job) or {})


def test_refusal_is_none_when_the_owner_has_an_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "settings.db"
    _seed(db, "u-a", [_account("sa-a", "Alpha", "key-alpha-1111", "alpha")], "sa-a")
    _point_at(monkeypatch, db)

    assert sermonaudio_refusal(_job("u-a")) is None
