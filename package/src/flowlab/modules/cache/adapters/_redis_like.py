from __future__ import annotations

import pickle
from typing import Any

from flowlab.modules.cache.adapters._base import AdapterABC

# EXISTS then INCRBY then PEXPIRE in one script, so the ttl is set exactly once: when the counter is created.
INCREMENT_SCRIPT = """
local created = redis.call('EXISTS', KEYS[1]) == 0
local value = redis.call('INCRBY', KEYS[1], ARGV[1])
if created and ARGV[2] ~= '' then
    redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return value
"""


class RedisLikeAdapter(AdapterABC):
    """Shared implementation for clients that speak the Redis wire protocol (redis-py, valkey-py)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, key: str) -> Any:
        raw = self._client.get(key)

        if raw is None:
            return None

        return pickle.loads(raw)

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        px = int(ttl * 1000) if ttl is not None else None
        self._client.set(key, pickle.dumps(value), px=px)

    def add(self, key: str, value: Any, ttl: float | None = None) -> bool:
        px = int(ttl * 1000) if ttl is not None else None
        return bool(self._client.set(key, pickle.dumps(value), px=px, nx=True))

    def increment(self, key: str, amount: int = 1, ttl: float | None = None) -> int:
        px = str(max(1, int(ttl * 1000))) if ttl is not None else ""
        return int(self._client.eval(INCREMENT_SCRIPT, 1, key, amount, px))

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def exists(self, key: str) -> bool:
        return bool(self._client.exists(key))

    def clear(self) -> None:
        self._client.flushdb()

    def close(self) -> None:
        self._client.close()
