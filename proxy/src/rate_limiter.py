import asyncio
import time
from dataclasses import dataclass


@dataclass
class Bucket:
    tokens: float
    last_refill: float


class TokenBucketLimiter:
    """Per-client token bucket. One instance per rate tier."""

    def __init__(self, rate_per_second: float, capacity: float):
        self.rate = rate_per_second
        self.capacity = capacity
        self.buckets: dict[str, Bucket] = {}
        self._lock = asyncio.Lock()

    async def allow(self, client_id: str) -> bool:
        async with self._lock:
            now = time.monotonic()
            bucket = self.buckets.get(client_id)

            if bucket is None:
                self.buckets[client_id] = Bucket(tokens=self.capacity - 1, last_refill=now)
                return True

            elapsed = now - bucket.last_refill
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.rate)
            bucket.last_refill = now

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True
            return False
