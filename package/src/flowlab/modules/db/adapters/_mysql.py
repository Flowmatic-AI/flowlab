from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from flowlab.modules.db import AdapterError
from flowlab.modules.db._threading import ThreadLocalStore
from flowlab.modules.db.adapters._base import AdapterABC
from flowlab.modules.db.result import MySQLResult, ResultABC

if TYPE_CHECKING:
    from mysql.connector.abstracts import MySQLConnectionAbstract, MySQLCursorAbstract
    from mysql.connector.types import RowItemType, RowType

    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.dialects import DialectABC


class MySQLAdapter(AdapterABC):
    def __init__(
        self,
        database_name: str,
        startup_queries: list[str] | None = None,
        options: dict[str, Any] | None = None,
        debug_callback: Callable[[str, float, str | None], None] | None = None,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        max_concurrent_connections: int | None = None,
        acquire_connection_timeout: float | None = None,
    ) -> None:
        super().__init__(
            driver_name="mysql",
            database_name=database_name,
            startup_queries=startup_queries,
            options=options,
            debug_callback=debug_callback,
            max_concurrent_connections=max_concurrent_connections,
            acquire_connection_timeout=acquire_connection_timeout,
        )
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._connections: ThreadLocalStore[MySQLConnectionAbstract] = ThreadLocalStore(
            on_thread_exit=self._close_connection,
            max_values=max_concurrent_connections,
            acquire_timeout=acquire_connection_timeout,
        )
        self._cursors: ThreadLocalStore[MySQLCursorAbstract] = ThreadLocalStore(
            on_thread_exit=self._close_cursor,
        )
        self._connect()

    @property
    def _connection(self) -> MySQLConnectionAbstract:
        connection = self._connections.current()
        if connection is not None:
            return connection

        self._ensure_not_closed()
        self._close_orphaned_connections()
        self._connect()
        return self._connections.require()

    def _close_connection(self, connection: MySQLConnectionAbstract) -> None:
        import mysql.connector

        with contextlib.suppress(mysql.connector.Error):
            connection.close()

    def _close_cursor(self, cursor: MySQLCursorAbstract) -> None:
        import mysql.connector

        with contextlib.suppress(mysql.connector.Error):
            cursor.close()

    def _close_orphaned_connections(self) -> None:
        for connection in self._connections.take_orphaned():
            self._close_connection(connection)

    def connection_count(self) -> int:
        return self._connections.count()

    def _connect(self) -> None:
        # A cursor from a previous connection cannot be drained on the new one.
        self._cursors.discard()

        # The slot is claimed before the handle is opened -- opening first and
        # counting after is exactly what the limit exists to prevent.
        with self._connections.reserve():
            self._connections.set(self._open_connection())
            self._closed = False

        if "charset" in self._options:
            collation = self._options.get("collation")
            names_sql = f"SET NAMES {self._options['charset']}"
            if collation:
                names_sql += f" COLLATE {collation}"
            self.exec(names_sql)

        if "engine" in self._options:
            self.exec(f"SET SESSION default_storage_engine = {self._options['engine']}")

        self._exec_startup_queries()

    def _open_connection(self) -> MySQLConnectionAbstract:
        import mysql.connector
        from mysql.connector.pooling import PooledMySQLConnection

        connect_options: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "database": self._database_name,
            "user": self._user,
            "password": self._password,
            "autocommit": True,
        }

        ssl_mode = self._options.get("ssl_mode")
        if ssl_mode:
            connect_options["ssl_mode"] = ssl_mode

        connect_timeout = self._options.get("connect_timeout")
        if connect_timeout:
            connect_options["connect_timeout"] = connect_timeout

        charset = self._options.get("charset", "utf8mb4")
        connect_options["charset"] = charset

        connection = mysql.connector.connect(**connect_options)
        if isinstance(connection, PooledMySQLConnection):
            raise AdapterError("pooled MySQL connections are not supported")

        return connection

    def _disconnect(self) -> None:
        self._cursors.discard()
        connection = self._connections.discard()
        if connection is not None:
            connection.close()

    def is_connected(self) -> bool:
        connection = self._connections.current()
        if connection is None:
            return False

        return connection.is_connected()

    def _drain_cursor(self) -> None:
        cursor = self._cursors.discard()
        if cursor is not None:
            import mysql.connector

            with contextlib.suppress(mysql.connector.Error):
                cursor.fetchall()

    @staticmethod
    def _first_column(row: RowType | dict[str, RowItemType]) -> RowItemType:
        if isinstance(row, dict):
            return next(iter(row.values()))
        return row[0]

    def version(self) -> str:
        import mysql.connector

        try:
            self._drain_cursor()
            cursor = self._connection.cursor()
            cursor.execute("SELECT VERSION()")
            row = cursor.fetchone()
            if row:
                return str(self._first_column(row))
            return "0"
        except mysql.connector.Error:
            return "0"

    def exec(self, query: str) -> None:
        start = time.time()
        error: str | None = None
        try:
            self._drain_cursor()
            cursor = self._connection.cursor()
            cursor.execute(query)
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = time.time() - start
            self._debug(query, duration, error)

    def query(self, query: str) -> ResultABC:
        start = time.time()
        error: str | None = None
        try:
            self._drain_cursor()
            cursor = self._connection.cursor()
            cursor.execute(query)
            self._cursors.set(cursor)
            return MySQLResult(cursor)
        except Exception as e:
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
        query_with_params = query_with_params.question_marks_to_percent_s()
        sql = query_with_params.query
        params = [dialect.cast_to_driver(param) for param in query_with_params.params]

        start = time.time()
        error: str | None = None
        try:
            self._drain_cursor()
            if emulate_prepare:
                sql_full = query_with_params.to_sql(dialect)
                cursor = self._connection.cursor()
                cursor.execute(sql_full)
            else:
                cursor = self._connection.cursor()
                cursor.execute(sql, params)
            self._cursors.set(cursor)
            return MySQLResult(cursor)
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = time.time() - start
            self._debug(query_with_params.to_sql(dialect), duration, error)

    @property
    def in_transaction(self) -> bool:
        return bool(self._connection.in_transaction)

    def last_insert_id(self, name: str | None = None) -> int | str | None:
        self._drain_cursor()
        cursor = self._connection.cursor()
        cursor.execute("SELECT LAST_INSERT_ID()")
        row = cursor.fetchone()
        if not row:
            return None
        value = self._first_column(row)
        if value is None or isinstance(value, (int, str)):
            return value
        raise AdapterError(f"unexpected LAST_INSERT_ID() result type: {type(value).__name__}")

    def get_connection(self) -> Any:
        return self._connection

    def close(self) -> None:
        if self._options.get("persistent", False):
            return

        self._cursors.take_all()

        for connection in self._connections.take_all():
            self._close_connection(connection)

        self._closed = True
