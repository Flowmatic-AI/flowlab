from __future__ import annotations

import math
import pickle
from typing import Any

from flowlab.modules.cache.adapters._base import AdapterABC


class MemcachedAdapter(AdapterABC):
    def __init__(self, host: str = "localhost", port: int = 11211, **options: Any) -> None:
        from pymemcache.client.base import Client

        self._client = Client((host, port), **options)

    @staticmethod
    def _expire(ttl: float | None) -> int:
        # Memcached expiration is second-granularity; round up so a sub-second
        # ttl still expires rather than silently rounding down to "never" (0).
        return 0 if ttl is None else max(1, math.ceil(ttl))

    def get(self, key: str) -> Any:
        raw = self._client.get(key)

        if raw is None:
            return None

        return pickle.loads(raw)

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._client.set(key, pickle.dumps(value), expire=self._expire(ttl))

    def add(self, key: str, value: Any, ttl: float | None = None) -> bool:
        return bool(self._client.add(key, pickle.dumps(value), expire=self._expire(ttl), noreply=False))

    def increment(self, key: str, amount: int = 1, ttl: float | None = None) -> int:
        # Memcached counters are unsigned: a decrement stops at zero.
        while True:
            value = self._client.incr(key, amount) if amount >= 0 else self._client.decr(key, -amount)

            if value is not None:
                return int(value)

            if self._client.add(key, str(max(amount, 0)).encode(), expire=self._expire(ttl), noreply=False):
                return max(amount, 0)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def exists(self, key: str) -> bool:
        return self._client.get(key) is not None

    def clear(self) -> None:
        self._client.flush_all()

    def close(self) -> None:
        self._client.close()
