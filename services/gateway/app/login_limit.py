"""Limit on failed logins, kept in gateway memory.

A key is the email from the login body, or from the OAuth consent form, plus
the client IP: both check the same password, so they share the count. Only
answers 401 from identity count; a successful login clears the key. After MAX_FAILURES
failures inside one window every login for that key gets 429 until the window
ends, the right password included. A restart forgets every counter.
"""

import json
import math
import time
from dataclasses import dataclass
from urllib.parse import parse_qs

from kvyt_common import DomainError

MAX_FAILURES = 5
WINDOW_SECONDS = 60


@dataclass
class _Window:
    started: float
    failures: int


class LoginLimiter:
    def __init__(self, max_failures: int = MAX_FAILURES, window_seconds: float = WINDOW_SECONDS) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._windows: dict[tuple[str, str], _Window] = {}

    @staticmethod
    def key(body: bytes, client_ip: str) -> tuple[str, str] | None:
        """None when the body carries no email; identity answers such a request with 422."""
        try:
            email = json.loads(body).get("email")
        except (ValueError, AttributeError):
            return None
        return LoginLimiter._key(email, client_ip)

    @staticmethod
    def form_key(body: bytes, client_ip: str) -> tuple[str, str] | None:
        """Key of an OAuth consent form that tries to log in, None for any other submit."""
        form = parse_qs(body.decode("utf-8", "replace"))
        if form.get("decision", [""])[0] != "allow":
            return None
        return LoginLimiter._key(form.get("email", [""])[0], client_ip)

    @staticmethod
    def _key(email, client_ip: str) -> tuple[str, str] | None:
        if not isinstance(email, str) or not email.strip():
            return None
        return email.strip().lower(), client_ip

    def _current(self, key: tuple[str, str], now: float) -> _Window | None:
        window = self._windows.get(key)
        if window is not None and now - window.started >= self.window_seconds:
            del self._windows[key]
            return None
        return window

    def check(self, key: tuple[str, str]) -> None:
        """Raises 429 while the key has used up its failures in the current window."""
        now = time.monotonic()
        window = self._current(key, now)
        if window is None or window.failures < self.max_failures:
            return
        retry_after = max(1, math.ceil(window.started + self.window_seconds - now))
        raise DomainError(
            "too_many_attempts",
            "Too many failed login attempts, try again later",
            429,
            headers={"Retry-After": str(retry_after)},
        )

    def record(self, key: tuple[str, str], status_code: int, succeeded: bool) -> None:
        if succeeded:
            self._windows.pop(key, None)
        elif status_code == 401:
            now = time.monotonic()
            window = self._current(key, now)
            if window is None:
                self._windows[key] = _Window(started=now, failures=1)
            else:
                window.failures += 1
