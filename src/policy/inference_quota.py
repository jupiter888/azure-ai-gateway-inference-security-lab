"""
Process-local inference quotas.

Fixed windows begin with the first admitted request.
State is bounded and protected against concurrent access.
Counters reset on process restart.
"""

import math
import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str
    retry_after: int | None = None


@dataclass
class Window:
    started: float
    count: int


class InferenceQuota:
    def __init__(
        self,
        limits: dict[str, int],
        window_seconds: int = 60,
        max_entries: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ):
        if (
            not limits
            or any(
                not isinstance(model, str)
                or not model
                or type(limit) is not int
                or limit < 1
                for model, limit in limits.items()
            )
            or type(window_seconds) is not int
            or window_seconds < 1
            or type(max_entries) is not int
            or max_entries < 1
        ):
            raise ValueError("Invalid quota configuration")

        self._limits = dict(limits)
        self._window_seconds = window_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._windows: dict[tuple[str, str], Window] = {}
        self._lock = Lock()

    def admit(self, subject: str, model: str) -> QuotaDecision:
        if (
            not isinstance(subject, str)
            or not subject
            or len(subject) > 8192
        ):
            return QuotaDecision(False, "invalid_subject")

        limit = self._limits.get(model)

        if limit is None:
            return QuotaDecision(False, "unknown_model")

        with self._lock:
            now = self._clock()

            expired = [
                key
                for key, window in self._windows.items()
                if now - window.started >= self._window_seconds
            ]
            for key in expired:
                del self._windows[key]

            key = (subject, model)
            window = self._windows.get(key)

            if window is None:
                if len(self._windows) >= self._max_entries:
                    return QuotaDecision(
                        False,
                        "capacity_exhausted",
                        retry_after=1,
                    )

                window = Window(started=now, count=0)
                self._windows[key] = window

            if window.count >= limit:
                retry_after = max(
                    1,
                    math.ceil(
                        self._window_seconds - (now - window.started)
                    ),
                )
                return QuotaDecision(
                    False,
                    "quota_exceeded",
                    retry_after=retry_after,
                )

            window.count += 1
            return QuotaDecision(True, "admitted")