from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.cache.adapters._base import AdapterABC

if TYPE_CHECKING:
    from flowlab.modules.db.database import DB


class Cache:
    def __init__(self, adapter: AdapterABC) -> None:
        self._adapter = adapter

    @classmethod
    def connect_redis(
        cls,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        **options: Any,
    ) -> Self:
        from flowlab.modules.cache.adapters._redis import RedisAdapter

        return cls(RedisAdapter(host=host, port=port, db=db, password=password, **options))

    @classmethod
    def connect_valkey(
        cls,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        **options: Any,
    ) -> Self:
        from flowlab.modules.cache.adapters._valkey import ValkeyAdapter

        return cls(ValkeyAdapter(host=host, port=port, db=db, password=password, **options))

    @classmethod
    def connect_memcached(
        cls,
        host: str = "localhost",
        port: int = 11211,
        **options: Any,
    ) -> Self:
        from flowlab.modules.cache.adapters._memcached import MemcachedAdapter

        return cls(MemcachedAdapter(host=host, port=port, **options))

    @classmethod
    def connect_database(cls, db: DB, table: str = "cache") -> Self:
        from flowlab.modules.cache.adapters._database import DatabaseAdapter

        return cls(DatabaseAdapter(db, table))

    @classmethod
    def shared_memory(cls) -> Self:
        from flowlab.modules.cache.adapters._shared_memory import SharedMemoryAdapter

        return cls(SharedMemoryAdapter())

    def get(self, key: str) -> Any:
        return self._adapter.get(key)

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._adapter.set(key, value, ttl)

    def delete(self, key: str) -> None:
        self._adapter.delete(key)

    def exists(self, key: str) -> bool:
        return self._adapter.exists(key)

    def add(self, key: str, value: Any, ttl: float | None = None) -> bool:
        """Set ``key`` only if it isn't already present. Returns whether it was set."""
        return self._adapter.add(key, value, ttl)

    def increment(self, key: str, amount: int = 1, ttl: float | None = None) -> int:
        """Atomically add ``amount`` to the counter at ``key`` and return the new value.

        A missing or expired counter starts from zero, and ``ttl`` only applies when the counter is created, so it
        expires ``ttl`` seconds after its first increment. Counters are stored as plain integers: read one with
        ``increment(key, 0)``, not ``get``.
        """
        return self._adapter.increment(key, amount, ttl)

    def decrement(self, key: str, amount: int = 1, ttl: float | None = None) -> int:
        """``increment`` by ``-amount``. Memcached counters stop at zero."""
        return self._adapter.increment(key, -amount, ttl)

    def pull(self, key: str, default: Any = None) -> Any:
        """Get ``key`` and delete it in one call."""
        value = self.get(key)
        self.delete(key)
        return value if value is not None else default

    def remember(self, key: str, callback: Callable[[], Any], ttl: float | None = None) -> Any:
        """Get ``key``, or compute it with ``callback`` and store it if missing or expired."""
        value = self.get(key)

        if value is not None:
            return value

        value = callback()
        self.set(key, value, ttl)
        return value

    def clear(self) -> None:
        self._adapter.clear()

    def close(self) -> None:
        self._adapter.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
