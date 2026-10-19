from __future__ import annotations

from collections import deque
from threading import Lock
import time


class RateLimiter:
    """Small process-local sliding-window limiter for local/deployed single workers."""

    def __init__(self, maximum: int, window_seconds: int = 60) -> None:
        self.maximum = maximum
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.maximum:
                return False
            events.append(now)
            if len(self._events) > 1000:
                self._events = {name: values for name, values in self._events.items() if values and values[-1] > cutoff}
            return True
