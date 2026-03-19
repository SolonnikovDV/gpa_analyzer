from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, DefaultDict, Tuple


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class InMemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._lock = threading.Lock()
        self._events: DefaultDict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> RateLimitDecision:
        now = time.time()
        with self._lock:
            bucket = self._events[key]
            boundary = now - self.window_seconds
            while bucket and bucket[0] <= boundary:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = max(1, int(bucket[0] + self.window_seconds - now))
                return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
            bucket.append(now)
            return RateLimitDecision(allowed=True, retry_after_seconds=0)
