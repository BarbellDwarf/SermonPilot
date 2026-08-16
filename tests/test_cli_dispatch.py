"""Fast tests for ``cli_main`` subcommand dispatch.

The documented subcommands are ``new-sermon``, ``sermon-update``,
``metadata-update``, ``validation``, and ``list``; ``process`` and
``validate`` are accepted aliases.  Handlers are patched so no processing
or network activity happens.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

import sermon_updater as su


def test_cli_main_dispatches_new_sermon(monkeypatch) -> None:
    handler = Mock()
    monkeypatch.setattr(su, "handle_new_sermon", handler)
    su.cli_main(["new-sermon", "audio.mp3", "--speaker", "Test Speaker", "--date", "2024-01-01"])
    handler.assert_called_once()


def test_cli_main_dispatches_process(monkeypatch) -> None:
    handler = Mock()
    monkeypatch.setattr(su, "handle_sermon_update", handler)
    su.cli_main(["process", "--sermon-id", "123"])
    handler.assert_called_once()


def test_cli_main_dispatches_sermon_update(monkeypatch) -> None:
    handler = Mock()
    monkeypatch.setattr(su, "handle_sermon_update", handler)
    su.cli_main(["sermon-update", "--sermon-id", "123"])
    handler.assert_called_once()


def test_cli_main_dispatches_metadata_update(monkeypatch) -> None:
    handler = Mock()
    monkeypatch.setattr(su, "handle_metadata_update", handler)
    su.cli_main(["metadata-update", "--sermon-id", "123"])
    handler.assert_called_once()


def test_cli_main_dispatches_validation(monkeypatch) -> None:
    handler = Mock()
    monkeypatch.setattr(su, "handle_validation", handler)
    su.cli_main(["validation", "--validate-descriptions"])
    handler.assert_called_once()


def test_cli_main_dispatches_validate(monkeypatch) -> None:
    handler = Mock()
    monkeypatch.setattr(su, "handle_validation", handler)
    su.cli_main(["validate", "--validate-descriptions"])
    handler.assert_called_once()


def test_cli_main_dispatches_list(monkeypatch) -> None:
    handler = Mock()
    monkeypatch.setattr(su, "handle_list_sermons", handler)
    su.cli_main(["list"])
    handler.assert_called_once()


def test_cli_main_without_command_prints_help(monkeypatch) -> None:
    assert su.cli_main([]) is None


def test_cli_main_unknown_command_errors(monkeypatch) -> None:
    with pytest.raises(SystemExit):
        su.cli_main(["bogus-command"])
