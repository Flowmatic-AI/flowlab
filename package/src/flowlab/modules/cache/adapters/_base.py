from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AdapterABC(ABC):
    @abstractmethod
    def get(self, key: str) -> Any: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: float | None = None) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def increment(self, key: str, amount: int = 1, ttl: float | None = None) -> int:
        """Atomically add ``amount`` to the counter at ``key`` and return the new value. A missing or expired
        counter starts from zero, and ``ttl`` only applies when the counter is created."""

    def add(self, key: str, value: Any, ttl: float | None = None) -> bool:
        """Set ``key`` only if it isn't already present. Not atomic by default — adapters
        that support a native check-and-set override this."""
        if self.exists(key):
            return False

        self.set(key, value, ttl)
        return True

    def close(self) -> None:
        pass
