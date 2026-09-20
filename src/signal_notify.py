"""Minimal Signal gateway client for the ingest watcher.

Talks to the self-hosted signal-cli-rest-api gateway using its ``v2/send``
shape. Configuration comes from the environment only:

  INGEST_SIGNAL_URL         gateway base URL (default http://192.0.2.22:8080)
  INGEST_SIGNAL_SENDER      sending account number or group id
  INGEST_SIGNAL_RECIPIENTS  comma/space separated recipient numbers or group ids

When the sender or recipients are unset the notifier is disabled and every
send is a no-op, so the watcher can run detection-only. A failed send logs and
returns False so the caller can retry on the next poll; it never raises.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_GATEWAY_URL = "http://192.0.2.22:8080"
DEFAULT_TIMEOUT = 10.0

_PLACEHOLDER_RE = re.compile(r"^\$\{[^}]+\}$")

_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB")


def clean(value: Any) -> str:
    """Return a stripped string, treating blanks and unexpanded ${VAR} as empty."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or _PLACEHOLDER_RE.match(value):
        return ""
    return value


def human_size(num_bytes: int | float) -> str:
    """Format a byte count for a notification: 1536 -> '1.5 KB'."""
    size = float(num_bytes)
    for unit in _SIZE_UNITS:
        if size < 1024 or unit == _SIZE_UNITS[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def parse_recipients(value: Any) -> list[str]:
    """Split a comma or whitespace separated recipient string into a list."""
    if not value:
        return []
    if isinstance(value, list | tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part for part in re.split(r"[,\s]+", str(value)) if part]


def build_detection_message(
    filename: str,
    size_bytes: int | float,
    duration_seconds: float | None = None,
    suggested_date: str | None = None,
) -> str:
    """Build the notification body.

    Duration is included only when the caller could obtain it cheaply; the
    watcher never streams the remote file to probe it, so it is usually absent.
    The suggested date is parsed from the filename and is a hint, not a fact.
    """
    parts = [f"New recording detected: {filename} ({human_size(size_bytes)})"]
    if duration_seconds is not None:
        parts.append(f"Duration: {duration_seconds:.0f}s")
    if suggested_date:
        parts.append(f"Suggested date: {suggested_date}")
    return " | ".join(parts)


class SignalNotifier:
    """Send ingest notifications through the Signal gateway."""

    def __init__(
        self,
        url: str | None = None,
        sender: str | None = None,
        recipients: Any = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.url = clean(url) or clean(os.environ.get("INGEST_SIGNAL_URL")) or DEFAULT_GATEWAY_URL
        self.sender = clean(sender) or clean(os.environ.get("INGEST_SIGNAL_SENDER"))
        self.recipients = parse_recipients(
            recipients if recipients else os.environ.get("INGEST_SIGNAL_RECIPIENTS")
        )
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.sender and self.recipients)

    def send(self, message: str) -> bool:
        """POST a message to ``/v2/send``. Returns False on any failure."""
        if not self.enabled:
            logger.info("ingest watcher: notify disabled (no sender/recipients configured)")
            return True
        payload = {
            "message": message,
            "number": self.sender,
            "recipients": self.recipients,
        }
        endpoint = f"{self.url.rstrip('/')}/v2/send"
        try:
            response = httpx.post(endpoint, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - notify must never crash the watcher
            logger.warning("ingest watcher: signal notify failed: %s", exc)
            return False
        return True

    def notify_recording(
        self,
        filename: str,
        size_bytes: int | float,
        suggested_date: str | None = None,
        duration_seconds: float | None = None,
    ) -> bool:
        message = build_detection_message(filename, size_bytes, duration_seconds, suggested_date)
        return self.send(message)
