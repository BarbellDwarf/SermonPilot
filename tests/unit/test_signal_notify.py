from __future__ import annotations

from src import signal_notify


class _Resp:
    status_code = 200

    def raise_for_status(self) -> None:
        return None


def test_default_gateway_url(monkeypatch):
    monkeypatch.delenv("INGEST_SIGNAL_URL", raising=False)
    notifier = signal_notify.SignalNotifier(sender="+1555", recipients="+1666")
    assert notifier.url == signal_notify.DEFAULT_GATEWAY_URL


def test_payload_shape(monkeypatch):
    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(signal_notify.httpx, "post", fake_post)
    notifier = signal_notify.SignalNotifier(
        url="http://gateway:8080/", sender="+1555", recipients="group.abc, +1666"
    )
    assert notifier.enabled is True
    assert notifier.notify_recording(
        "service_2026-09-20_10-11-12.mkv", 12 * 1024 * 1024, "2026-09-20 10:11:12"
    )

    assert captured["url"] == "http://gateway:8080/v2/send"
    body = captured["json"]
    assert body["number"] == "+1555"
    assert body["recipients"] == ["group.abc", "+1666"]
    assert "service_2026-09-20_10-11-12.mkv" in body["message"]
    assert "12.0 MB" in body["message"]
    assert "2026-09-20 10:11:12" in body["message"]


def test_disabled_without_sender_or_recipients(monkeypatch):
    monkeypatch.delenv("INGEST_SIGNAL_SENDER", raising=False)
    monkeypatch.delenv("INGEST_SIGNAL_RECIPIENTS", raising=False)
    notifier = signal_notify.SignalNotifier()
    assert notifier.enabled is False
    assert notifier.send("hello") is True


def test_failure_logs_and_returns_false(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(signal_notify.httpx, "post", boom)
    notifier = signal_notify.SignalNotifier(sender="+1", recipients="+2")
    assert notifier.notify_recording("x.wav", 100) is False


def test_http_error_response_returns_false(monkeypatch):
    class _Bad:
        status_code = 500

        def raise_for_status(self) -> None:
            raise RuntimeError("500 Server Error")

    monkeypatch.setattr(signal_notify.httpx, "post", lambda *a, **k: _Bad())
    notifier = signal_notify.SignalNotifier(sender="+1", recipients="+2")
    assert notifier.notify_recording("x.wav", 100) is False


def test_human_size():
    assert signal_notify.human_size(0) == "0 B"
    assert signal_notify.human_size(1536) == "1.5 KB"
    assert signal_notify.human_size(50 * 1024 * 1024) == "50.0 MB"


def test_unexpanded_placeholder_is_treated_as_unset():
    notifier = signal_notify.SignalNotifier(
        url="${INGEST_SIGNAL_URL}", sender="${INGEST_SIGNAL_SENDER}", recipients=""
    )
    assert notifier.url == signal_notify.DEFAULT_GATEWAY_URL
    assert notifier.enabled is False
