import asyncio
import time
from collections import deque


class RateLimiter:
    """At most `calls` acquisitions per rolling `period` seconds."""

    def __init__(self, calls: int, period: float):
        self.calls, self.period = calls, period
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._stamps and now - self._stamps[0] >= self.period:
                    self._stamps.popleft()
                if len(self._stamps) < self.calls:
                    self._stamps.append(now)
                    return
                await asyncio.sleep(self.period - (now - self._stamps[0]) + 0.05)
