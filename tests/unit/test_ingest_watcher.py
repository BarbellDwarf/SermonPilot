from __future__ import annotations

import shutil

import pytest

from src import ingest_watcher
from src.ingest_watcher import RemoteFile, WatcherState, load_settings

MB = 1024 * 1024
FIXED_MTIME = "2026-09-20 10:11:12"


def make_settings(**overrides) -> ingest_watcher.WatcherSettings:
    block = {
        "enabled": True,
        "remote": "cloud-remote",
        "user_id": "admin",
        "poll_interval_seconds": 60,
        "stability_window_seconds": 300,
        "size_floor_mb": 0,
        "extension_allowlist": [".mkv", ".mp4"],
        "state_file": "/tmp/unused-state.json",
        "watch_subpath": "",
        "signal": {},
    }
    block.update(overrides)
    return load_settings({"ingest_watcher": block})


class FakeNotifier:
    enabled = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str | None]] = []

    def notify_recording(self, filename, size_bytes, suggested_date=None, duration_seconds=None):
        self.calls.append((filename, size_bytes, suggested_date))
        return True


class FlakyNotifier:
    enabled = True

    def __init__(self) -> None:
        self.calls = 0
        self.ok = False

    def notify_recording(self, filename, size_bytes, suggested_date=None, duration_seconds=None):
        self.calls += 1
        return self.ok


def test_parse_lsf_skips_directories_and_accepts_two_columns():
    text = "-1;2026-09-20 11:00:00;sub/\n5;2026-09-20 05:11:12;sub/a.mkv\n7;b.mp4"
    assert ingest_watcher.parse_lsf(text) == [
        RemoteFile("sub/a.mkv", 5, "2026-09-20 05:11:12"),
        RemoteFile("b.mp4", 7, ""),
    ]


def test_suggested_date_parses_filename():
    assert (
        ingest_watcher.suggested_date("Sermon Audio/service 2026-09-20_10-11-12.mkv")
        == "2026-09-20 10:11:12"
    )
    assert ingest_watcher.suggested_date("no-date-here.mkv") is None


def test_env_gate_enables_watcher(monkeypatch):
    monkeypatch.setenv("INGEST_WATCHER_ENABLED", "1")
    settings = load_settings({"ingest_watcher": {"enabled": False, "remote": "r"}})
    assert settings.enabled is True


def test_stability_new_then_stable_then_notified(tmp_path):
    settings = make_settings(state_file=str(tmp_path / "state.json"))
    state = WatcherState(tmp_path / "state.json")
    notifier = FakeNotifier()
    file = RemoteFile("svc/sermon_2026-09-20_10-11-12.mkv", 100 * MB, FIXED_MTIME)

    assert ingest_watcher.run_cycle(settings, state, [file], 0.0, notifier) == []
    assert ingest_watcher.run_cycle(settings, state, [file], 60.0, notifier) == []
    assert notifier.calls == []

    handled = ingest_watcher.run_cycle(settings, state, [file], 400.0, notifier)
    assert handled == [settings.state_key(file.path)]
    assert notifier.calls == [("sermon_2026-09-20_10-11-12.mkv", 100 * MB, file.path)]

    assert ingest_watcher.run_cycle(settings, state, [file], 460.0, notifier) == []
    assert len(notifier.calls) == 1


def test_size_change_resets_stability_window(tmp_path):
    settings = make_settings(state_file=str(tmp_path / "state.json"))
    state = WatcherState(tmp_path / "state.json")
    notifier = FakeNotifier()

    first = RemoteFile("a.mkv", 100 * MB, "2026-09-20 10:00:00")
    ingest_watcher.run_cycle(settings, state, [first], 0.0, notifier)
    changed = RemoteFile("a.mkv", 100 * MB, "2026-09-20 10:05:00")
    assert ingest_watcher.run_cycle(settings, state, [changed], 400.0, notifier) == []
    assert notifier.calls == []
    assert ingest_watcher.run_cycle(settings, state, [changed], 700.0, notifier) != []
    assert len(notifier.calls) == 1


def test_state_persists_across_restart_and_does_not_renotify(tmp_path):
    state_path = tmp_path / "state.json"
    settings = make_settings(state_file=str(state_path))
    file = RemoteFile("a.mkv", 100 * MB, FIXED_MTIME)

    state = WatcherState.load(state_path)
    ingest_watcher.run_cycle(settings, state, [file], 0.0, FakeNotifier())
    state.save()

    restarted = WatcherState.load(state_path)
    notifier = FakeNotifier()
    handled = ingest_watcher.run_cycle(settings, restarted, [file], 400.0, notifier)
    assert handled != []
    assert len(notifier.calls) == 1
    restarted.save()

    after = WatcherState.load(state_path)
    second = FakeNotifier()
    assert ingest_watcher.run_cycle(settings, after, [file], 1000.0, second) == []
    assert second.calls == []


def test_extension_allowlist_filters(tmp_path):
    settings = make_settings(state_file=str(tmp_path / "state.json"), extension_allowlist=[".mkv"])
    state = WatcherState(tmp_path / "state.json")
    notifier = FakeNotifier()
    mkv = RemoteFile("a.mkv", 100 * MB, FIXED_MTIME)
    txt = RemoteFile("notes.txt", 100 * MB, FIXED_MTIME)

    for now in (0.0, 400.0):
        ingest_watcher.run_cycle(settings, state, [mkv, txt], now, notifier)
    assert [call[0] for call in notifier.calls] == ["a.mkv"]


def test_size_floor_filters(tmp_path):
    settings = make_settings(state_file=str(tmp_path / "state.json"), size_floor_mb=50)
    state = WatcherState(tmp_path / "state.json")
    notifier = FakeNotifier()
    small = RemoteFile("small.mkv", 10 * MB, FIXED_MTIME)
    big = RemoteFile("big.mkv", 100 * MB, FIXED_MTIME)

    for now in (0.0, 400.0):
        ingest_watcher.run_cycle(settings, state, [small, big], now, notifier)
    assert [call[0] for call in notifier.calls] == ["big.mkv"]


def test_notify_failure_retries_next_cycle(tmp_path):
    settings = make_settings(state_file=str(tmp_path / "state.json"))
    state = WatcherState(tmp_path / "state.json")
    notifier = FlakyNotifier()
    file = RemoteFile("a.mkv", 100 * MB, FIXED_MTIME)

    for now in (0.0, 60.0, 400.0):
        assert ingest_watcher.run_cycle(settings, state, [file], now, notifier) == []
    assert notifier.calls == 1

    notifier.ok = True
    assert ingest_watcher.run_cycle(settings, state, [file], 410.0, notifier) != []
    assert notifier.calls == 2


def test_disabled_config_is_noop(monkeypatch, tmp_path):
    monkeypatch.delenv("INGEST_WATCHER_ENABLED", raising=False)
    settings = make_settings(enabled=False, state_file=str(tmp_path / "state.json"))

    def boom(*args, **kwargs):
        raise AssertionError("rclone must not run when the watcher is disabled")

    monkeypatch.setattr(ingest_watcher, "list_remote_files", boom)
    assert ingest_watcher.run(settings, max_cycles=1) == 0


def test_run_detection_only_marks_state(monkeypatch, tmp_path):
    monkeypatch.delenv("INGEST_SIGNAL_SENDER", raising=False)
    monkeypatch.delenv("INGEST_SIGNAL_RECIPIENTS", raising=False)
    settings = make_settings(state_file=str(tmp_path / "state.json"), stability_window_seconds=0)
    file = RemoteFile("a.mkv", 100 * MB, FIXED_MTIME)
    monkeypatch.setattr(
        ingest_watcher, "list_remote_files", lambda settings, **kwargs: [file]
    )

    assert ingest_watcher.run(settings, max_cycles=2, sleep=lambda *_: None) == 0
    entry = WatcherState.load(settings.state_file).get(settings.state_key("a.mkv"))
    assert entry is not None and entry["notified"] is True


def test_list_remote_files_command(monkeypatch, tmp_path):
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    config = tmp_path / "rclone" / "admin" / "config"
    config.parent.mkdir(parents=True)
    config.write_text("[cloud-remote]\ntype=drive\n", encoding="utf-8")
    monkeypatch.setattr(ingest_watcher.shutil, "which", lambda name: "/usr/bin/rclone")

    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = "5;2026-09-20 10:00:00;sub/a.mkv\n-1;sub/;2026-09-20 10:00:00\n"
        stderr = ""

    def runner(args, **kwargs):
        captured["args"] = args
        return _Proc()

    settings = make_settings(remote="cloud-remote", user_id="admin", watch_subpath="Sermon Audio/")
    files = ingest_watcher.list_remote_files(settings, runner=runner)

    args = captured["args"]
    assert args[:3] == ["/usr/bin/rclone", "--config", str(config)]
    assert "lsf" in args
    assert "cloud-remote:Sermon Audio/" in args
    assert "--recursive" in args
    assert args[args.index("--format") + 1] == "stp"
    assert [file.path for file in files] == ["sub/a.mkv"]


def test_list_remote_files_failure_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    config = tmp_path / "rclone" / "admin" / "config"
    config.parent.mkdir(parents=True)
    config.write_text("[cloud-remote]\ntype=drive\n", encoding="utf-8")
    monkeypatch.setattr(ingest_watcher.shutil, "which", lambda name: "/usr/bin/rclone")

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "connection reset"

    settings = make_settings(remote="cloud-remote", user_id="admin")
    with pytest.raises(RuntimeError, match="connection reset"):
        ingest_watcher.list_remote_files(settings, runner=lambda *a, **k: _Proc())


def test_missing_rclone_config_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))
    monkeypatch.setattr(ingest_watcher.shutil, "which", lambda name: "/usr/bin/rclone")
    settings = make_settings(remote="cloud-remote", user_id="nobody")
    with pytest.raises(RuntimeError, match="config not found"):
        ingest_watcher.list_remote_files(settings, runner=lambda *a, **k: None)


def test_real_rclone_local_remote_when_available(monkeypatch, tmp_path):
    if not shutil.which("rclone"):
        pytest.skip("rclone not installed")
    monkeypatch.chdir(tmp_path)
    remote = tmp_path / "remote"
    remote.mkdir()
    (remote / "svc_2026-09-20_10-11-12.mkv").write_bytes(b"x" * 10)
    config = tmp_path / "rclone" / "admin" / "config"
    config.parent.mkdir(parents=True)
    config.write_text("[localtest]\ntype = local\n", encoding="utf-8")
    monkeypatch.setenv("SERMONPILOT_RCLONE_DIR", str(tmp_path / "rclone"))

    settings = make_settings(remote="localtest", user_id="admin", watch_subpath="remote")
    files = ingest_watcher.list_remote_files(settings)
    assert [file.path for file in files] == ["svc_2026-09-20_10-11-12.mkv"]

