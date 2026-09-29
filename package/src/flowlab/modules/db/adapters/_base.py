from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from flowlab.modules.db import AdapterError
from flowlab.modules.db.result import ResultABC

if TYPE_CHECKING:
    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.dialects import DialectABC


class AdapterABC(ABC):
    def __init__(
        self,
        driver_name: str,
        database_name: str,
        startup_queries: list[str] | None = None,
        options: dict[str, Any] | None = None,
        debug_callback: Callable[[str, float, str | None], None] | None = None,
        max_concurrent_connections: int | None = None,
        acquire_connection_timeout: float | None = None,
    ) -> None:
        if max_concurrent_connections is not None and max_concurrent_connections < 1:
            raise AdapterError("max_concurrent_connections must be at least 1")

        self._driver_name = driver_name
        self._database_name = database_name
        self._startup_queries = startup_queries or []
        self._options = options or {}
        self._debug_callback = debug_callback
        self._max_concurrent_connections = max_concurrent_connections
        self._acquire_connection_timeout = acquire_connection_timeout
        self._closed = False

    def _exec_startup_queries(self) -> None:
        for query in self._startup_queries:
            self.exec(query)

    def _debug(self, sql: str, duration: float, error: str | None = None) -> None:
        if self._debug_callback is not None:
            self._debug_callback(sql, duration, error)

    def _ensure_not_closed(self) -> None:
        if self._closed:
            raise AdapterError("this adapter is closed; call reconnect() to open a new connection")

    @property
    def closed(self) -> bool:
        return self._closed

    def connection_count(self) -> int:
        return 1 if self.is_connected() else 0

    @property
    def max_concurrent_connections(self) -> int | None:
        """Cap on live connections, or ``None`` when uncapped.

        A thread past the cap waits in :meth:`ThreadLocalStore.reserve` until a
        slot frees -- which happens when another thread exits, is swept as
        orphaned, or the adapter is closed."""
        return self._max_concurrent_connections

    @property
    def acquire_connection_timeout(self) -> float | None:
        return self._acquire_connection_timeout

    @property
    def driver_name(self) -> str:
        return self._driver_name

    @property
    def database_name(self) -> str:
        return self._database_name

    @abstractmethod
    def _connect(self) -> None: ...

    @abstractmethod
    def _disconnect(self) -> None:
        """Unconditionally drop the driver handle.

        Separate from :meth:`close`, which honours the ``persistent`` option and
        may deliberately leave the handle open."""

    @abstractmethod
    def is_connected(self) -> bool: ...

    def reconnect(self) -> None:
        """Throw the current connection away and open a fresh one.

        The old handle is very likely dead already -- that is what makes a
        reconnect necessary -- so failures while dropping it are ignored."""
        with contextlib.suppress(Exception):
            self._disconnect()

        self._closed = False
        self._connect()

    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def exec(self, query: str) -> None: ...

    @abstractmethod
    def query(self, query: str) -> ResultABC: ...

    @abstractmethod
    def query_with_params(
        self,
        dialect: DialectABC,
        query_with_params: QueryWithParams,
        emulate_prepare: bool = False,
    ) -> ResultABC: ...

    @property
    @abstractmethod
    def in_transaction(self) -> bool: ...

    def begin_transaction(self, sql: str) -> None:
        if self.in_transaction:
            return
        self.exec(sql)

    def commit_transaction(self, sql: str) -> None:
        if not self.in_transaction:
            return
        self.exec(sql)

    def rollback_transaction(self, sql: str) -> None:
        if not self.in_transaction:
            return
        self.exec(sql)

    def begin_savepoint(self, sql: str) -> None:
        if not self.in_transaction:
            return
        self.exec(sql)

    def commit_savepoint(self, sql: str) -> None:
        if not self.in_transaction:
            return
        self.exec(sql)

    def rollback_savepoint(self, sql: str) -> None:
        if not self.in_transaction:
            return
        self.exec(sql)

    @abstractmethod
    def last_insert_id(self, name: str | None = None) -> int | str | None: ...

    @abstractmethod
    def get_connection(self) -> Any: ...

    @abstractmethod
    def close(self) -> None: ...
