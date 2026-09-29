from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from flowlab.modules.db._json import decode_json, encode_json
from flowlab.modules.db._threading import ThreadLocalStore
from flowlab.modules.db.adapters._base import AdapterABC
from flowlab.modules.db.result import ResultABC, SQLite3Result

if TYPE_CHECKING:
    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.dialects import DialectABC

_REGISTRY_LOCK = threading.Lock()


def _adapt_datetime(value: datetime) -> str:
    """ISO-8601 with a space separator: keeps microseconds and the UTC offset
    (both of which the dialect's SQL-literal format drops) while staying
    readable to SQLite's own date/time functions."""
    return value.isoformat(sep=" ")


def _adapt_date(value: date) -> str:
    return value.isoformat()


def _adapt_json(value: dict[str, Any] | list[Any]) -> str:
    return encode_json(value)


def _convert_datetime(value: bytes) -> datetime | str:
    text = value.decode("utf-8")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return text


def _convert_date(value: bytes) -> date | str:
    text = value.decode("utf-8")
    try:
        return date.fromisoformat(text)
    except ValueError:
        return text


def _convert_json(value: bytes) -> Any:
    return decode_json(value)


def _convert_bool(value: bytes) -> bool:
    """SQLite has no boolean type -- ``cast_bool()`` stores 0/1 -- so a BOOLEAN
    column reads back as an integer unless it is converted here."""
    text = value.decode("utf-8").strip()

    if text.lstrip("+-").isdigit():
        return int(text) != 0

    return text.lower() in ("true", "t", "yes")


def _register_types() -> None:
    """Teach ``sqlite3`` the DATETIME/DATE, JSON and BOOLEAN column types SQLite
    itself does not have, in both directions.

    The ``sqlite3`` registry is a process-wide module singleton, so this is
    global state -- but the converters only fire on connections opened with
    ``PARSE_DECLTYPES``, which is exactly the connections this adapter opens.
    Registering is idempotent (each call overwrites the same registry entry),
    so it runs per connect instead of at import time.
    """
    with _REGISTRY_LOCK:
        sqlite3.register_adapter(datetime, _adapt_datetime)
        sqlite3.register_adapter(date, _adapt_date)
        sqlite3.register_adapter(dict, _adapt_json)
        sqlite3.register_adapter(list, _adapt_json)
        sqlite3.register_converter("DATETIME", _convert_datetime)
        sqlite3.register_converter("TIMESTAMP", _convert_datetime)
        sqlite3.register_converter("DATE", _convert_date)
        sqlite3.register_converter("JSON", _convert_json)
        sqlite3.register_converter("JSONB", _convert_json)
        sqlite3.register_converter("BOOLEAN", _convert_bool)
        sqlite3.register_converter("BOOL", _convert_bool)


def _is_memory_database(database_name: str) -> bool:
    if database_name in ("", ":memory:"):
        return True

    return database_name.startswith("file:") and "mode=memory" in database_name


def _cast_param(dialect: DialectABC, value: Any) -> Any:
    """Temporals and documents are left native so the registered ``sqlite3``
    adapters above serialize them; everything else goes through the dialect."""
    if isinstance(value, (datetime, date, dict, list)):
        return value
    return dialect.cast_to_driver(value)


class SQLiteAdapter(AdapterABC):
    def __init__(
        self,
        database_name: str = ":memory:",
        startup_queries: list[str] | None = None,
        options: dict[str, Any] | None = None,
        debug_callback: Callable[[str, float, str | None], None] | None = None,
        max_concurrent_connections: int | None = None,
        acquire_connection_timeout: float | None = None,
    ) -> None:
        super().__init__(
            driver_name="sqlite",
            database_name=database_name,
            startup_queries=startup_queries,
            options=options,
            debug_callback=debug_callback,
            max_concurrent_connections=max_concurrent_connections,
            acquire_connection_timeout=acquire_connection_timeout,
        )
        shared = _is_memory_database(database_name)
        self._connections: ThreadLocalStore[sqlite3.Connection] = ThreadLocalStore(
            shared_across_threads=shared,
            on_thread_exit=self._close_connection,
            max_values=max_concurrent_connections,
            acquire_timeout=acquire_connection_timeout,
        )
        self._statement_lock: AbstractContextManager[Any] = threading.RLock() if shared else nullcontext()
        self._connect()

    @property
    def _connection(self) -> sqlite3.Connection:
        connection = self._connections.current()
        if connection is not None:
            return connection

        self._ensure_not_closed()
        self._close_orphaned_connections()
        self._connect()
        return self._connections.require()

    def _close_connection(self, connection: sqlite3.Connection) -> None:
        with contextlib.suppress(sqlite3.Error):
            connection.close()

    def _close_orphaned_connections(self) -> None:
        for connection in self._connections.take_orphaned():
            self._close_connection(connection)

    def connection_count(self) -> int:
        return self._connections.count()

    def _connect(self) -> None:
        _register_types()

        # The slot is claimed before the handle is opened -- opening first and
        # counting after is exactly what the limit exists to prevent.
        with self._connections.reserve():
            self._connections.set(self._open_connection())
            self._closed = False

        self._exec_startup_queries()

    def _open_connection(self) -> sqlite3.Connection:
        db_name = self._database_name
        read_only = self._options.get("read_only", False)
        check_same_thread = self._options.get(
            "check_same_thread",
            not self._connections.shared_across_threads,
        )

        if read_only:
            uri = f"file:{db_name}?mode=ro"
            connection = sqlite3.connect(
                uri,
                uri=True,
                isolation_level=None,
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=check_same_thread,
            )
        else:
            connection = sqlite3.connect(
                db_name,
                uri=db_name.startswith("file:"),
                isolation_level=None,
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=check_same_thread,
            )

        connection.row_factory = sqlite3.Row

        connection.execute(f"PRAGMA journal_mode = {self._options.get('journal_mode', 'WAL')}")
        connection.execute(f"PRAGMA busy_timeout = {int(self._options.get('busy_timeout', 500))}")

        if "encryption_key" in self._options:
            connection.execute(f"PRAGMA key = '{self._options['encryption_key']}'")

        if "encoding" in self._options:
            connection.execute(f"PRAGMA encoding = '{self._options['encoding']}'")

        if self._options.get("foreign_keys", True):
            connection.execute("PRAGMA foreign_keys = ON")

        create_functions: dict[str, Any] = self._options.get("create_functions", {})

        if "REGEXP" not in create_functions:
            connection.create_function("REGEXP", 2, _regexp_fn)

        if "regexp_like" not in create_functions:
            connection.create_function("regexp_like", -1, _regexp_like_fn)

        for function_name, callback in create_functions.items():
            connection.create_function(function_name, -1, callback)

        return connection

    def _disconnect(self) -> None:
        connection = self._connections.discard()
        if connection is not None:
            connection.close()

    def is_connected(self) -> bool:
        connection = self._connections.current()
        if connection is None:
            return False

        try:
            # Cheapest attribute that still goes through sqlite3's
            # closed-connection check; raises ProgrammingError once closed.
            _ = connection.total_changes
        except sqlite3.Error:
            return False
        return True

    def version(self) -> str:
        try:
            with self._statement_lock:
                cursor = self._connection.execute("SELECT sqlite_version()")
                row = cursor.fetchone()
            return str(row[0]) if row else "0"
        except sqlite3.Error:
            return "0"

    def exec(self, query: str) -> None:
        start = time.time()
        error: str | None = None
        try:
            with self._statement_lock:
                self._connection.execute(query)
        except sqlite3.Error as e:
            error = str(e)
            raise
        finally:
            duration = time.time() - start
            self._debug(query, duration, error)

    def query(self, query: str) -> ResultABC:
        start = time.time()
        error: str | None = None
        try:
            with self._statement_lock:
                cursor = self._connection.execute(query)
            return SQLite3Result(cursor)
        except sqlite3.Error as e:
            error = str(e)
            raise
        finally:
            duration = time.time() - start
            self._debug(query, duration, error)

    def query_with_params(
        self,
        dialect: DialectABC,
        query_with_params: QueryWithParams,
        emulate_prepare: bool = False,
    ) -> ResultABC:
        query_with_params = query_with_params.percent_s_to_question_marks()
        sql = query_with_params.query
        params = [_cast_param(dialect, param) for param in query_with_params.params]

        start = time.time()
        error: str | None = None
        try:
            with self._statement_lock:
                if emulate_prepare:
                    sql_full = query_with_params.to_sql(dialect)
                    cursor = self._connection.execute(sql_full)
                else:
                    cursor = self._connection.execute(sql, params)
            return SQLite3Result(cursor)
        except sqlite3.Error as e:
            error = str(e)
            raise
        finally:
            duration = time.time() - start
            self._debug(query_with_params.to_sql(dialect), duration, error)

    @property
    def in_transaction(self) -> bool:
        return self._connection.in_transaction

    def last_insert_id(self, name: str | None = None) -> int | str | None:
        with self._statement_lock:
            cursor = self._connection.execute("SELECT last_insert_rowid()")
            row = cursor.fetchone()
        return row[0] if row else None

    def get_connection(self) -> Any:
        return self._connection

    def close(self) -> None:
        optimize = self._options.get("optimize", False)
        persistent = self._options.get("persistent", False)

        if not optimize and persistent:
            return

        with self._statement_lock:
            connections = self._connections.values() if persistent else self._connections.take_all()

            for connection in connections:
                if optimize:
                    with contextlib.suppress(sqlite3.Error):
                        connection.execute("PRAGMA optimize")

                if not persistent:
                    with contextlib.suppress(sqlite3.Error):
                        connection.close()

        if not persistent:
            self._closed = True


def _regexp_fn(pattern: str, value: str) -> int:
    import re

    try:
        return 1 if re.search(pattern, str(value)) else 0
    except re.error:
        return 0


def _regexp_like_fn(value: str, pattern: str, flags: str = "") -> int:
    import re

    try:
        py_flags = 0
        for flag in flags or "":
            py_flags |= {
                "i": re.IGNORECASE,
                "m": re.MULTILINE,
                "s": re.DOTALL,
                "x": re.VERBOSE,
            }.get(flag.lower(), 0)
        return 1 if re.search(pattern, str(value), py_flags) else 0
    except re.error:
        return 0
