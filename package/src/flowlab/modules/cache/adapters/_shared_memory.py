from __future__ import annotations

import threading
import time
from typing import Any

from flowlab.modules.cache.adapters._base import AdapterABC


class SharedMemoryAdapter(AdapterABC):
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self._store.get(key)

            if entry is None:
                return None

            value, expires_at = entry

            if expires_at is not None and expires_at < time.time():
                del self._store[key]
                return None

            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        expires_at = time.time() + ttl if ttl is not None else None

        with self._lock:
            self._store[key] = (value, expires_at)

    def add(self, key: str, value: Any, ttl: float | None = None) -> bool:
        with self._lock:
            entry = self._store.get(key)

            if entry is not None:
                _, expires_at = entry

                if expires_at is None or expires_at >= time.time():
                    return False

            expires_at = time.time() + ttl if ttl is not None else None
            self._store[key] = (value, expires_at)
            return True

    def increment(self, key: str, amount: int = 1, ttl: float | None = None) -> int:
        now = time.time()

        with self._lock:
            entry = self._store.get(key)

            if entry is None or (entry[1] is not None and entry[1] < now):
                value, expires_at = amount, now + ttl if ttl is not None else None
            else:
                value, expires_at = int(entry[0]) + amount, entry[1]

            self._store[key] = (value, expires_at)
            return value

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        with self._lock:
            entry = self._store.get(key)

            if entry is None:
                return False

            _, expires_at = entry

            if expires_at is not None and expires_at < time.time():
                del self._store[key]
                return False

            return True

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
