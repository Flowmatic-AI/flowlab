from __future__ import annotations

import asyncio
import contextlib
import re
import threading
import time
from collections.abc import Callable, Coroutine, Sequence
from datetime import date, datetime
from datetime import time as time_of_day
from typing import TYPE_CHECKING, Any, TypeVar

from flowlab.modules.db._json import decode_json, encode_json
from flowlab.modules.db._query_with_params import REGEX_PATTERN
from flowlab.modules.db._threading import ThreadLocalStore
from flowlab.modules.db.adapters._base import AdapterABC
from flowlab.modules.db.query.expressions import PostgresArray
from flowlab.modules.db.result import AsyncpgResult, PsycopgResult, ResultABC

if TYPE_CHECKING:
    import ssl

    from asyncpg import Connection as AsyncpgConnection
    from psycopg import Connection
    from psycopg.rows import TupleRow

    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.dialects import DialectABC

T = TypeVar("T")

_VERSION_PATTERN = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def _placeholders_to_dollar_signs(query: str) -> str:
    """asyncpg only speaks native PostgreSQL ``$1``-style placeholders, so both
    ``?`` and ``%s`` are numbered here (skipping literals and comments)."""
    index = 0

    def _replacer(match: re.Match[str]) -> str:
        nonlocal index
        if match.group(1) is not None or match.group(2) is not None:
            index += 1
            return f"${index}"
        return match.group(0)

    return REGEX_PATTERN.sub(_replacer, query)


_TEXT_TYPE_OIDS = frozenset({18, 19, 25, 705, 1042, 1043})

_JSON_TYPE_OIDS = frozenset({114, 3802})


def _cast_param(dialect: DialectABC, value: Any) -> Any:
    if isinstance(value, (datetime, date, time_of_day)):
        return value
    if isinstance(value, (dict, list, PostgresArray)):
        return value
    return dialect.cast_to_driver(value)


def _adapt_params(dialect: DialectABC, parameter_types: Sequence[Any], params: list[Any]) -> list[Any]:
    """Render temporal and document values bound to a text placeholder, using the
    prepared statement's parameter types — the only point where the target type
    is known.

    psycopg can hand PostgreSQL a datetime for a text column and let the server
    render it; asyncpg encodes binary against the declared type and refuses, so
    the dialect's cast is applied here instead.
    """
    adapted: list[Any] = []
    for index, value in enumerate(params):
        if index >= len(parameter_types):
            adapted.append(value)
            continue
        adapted.append(_adapt_param(dialect, parameter_types[index].oid, value))
    return adapted


def _adapt_param(dialect: DialectABC, oid: int, value: Any) -> Any:
    if isinstance(value, PostgresArray):
        return list(value.values)

    if isinstance(value, (datetime, date, time_of_day)):
        return dialect.cast_datetime(value) if oid in _TEXT_TYPE_OIDS else value

    if isinstance(value, (dict, list)):
        return value if oid in _JSON_TYPE_OIDS else dialect.cast_json(value)

    return value


class PsycopgAdapter(AdapterABC):
    def __init__(
        self,
        database_name: str,
        startup_queries: list[str] | None = None,
        options: dict[str, Any] | None = None,
        debug_callback: Callable[[str, float, str | None], None] | None = None,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        max_concurrent_connections: int | None = None,
        acquire_connection_timeout: float | None = None,
    ) -> None:
        super().__init__(
            driver_name="postgresql",
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
        self._connections: ThreadLocalStore[Connection[TupleRow]] = ThreadLocalStore(
            on_thread_exit=self._close_connection,
            max_values=max_concurrent_connections,
            acquire_timeout=acquire_connection_timeout,
        )
        self._connect()

    @property
    def _connection(self) -> Connection[TupleRow]:
        connection = self._connections.current()
        if connection is not None:
            return connection

        self._ensure_not_closed()
        self._close_orphaned_connections()
        self._connect()
        return self._connections.require()

    def _close_connection(self, connection: Connection[TupleRow]) -> None:
        import psycopg

        with contextlib.suppress(psycopg.Error):
            connection.close()

    def _close_orphaned_connections(self) -> None:
        for connection in self._connections.take_orphaned():
            self._close_connection(connection)

    def connection_count(self) -> int:
        return self._connections.count()

    def _connect(self) -> None:
        import psycopg

        connect_options: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "dbname": self._database_name,
            "user": self._user,
            "password": self._password,
            "autocommit": True,
        }

        if "ssl_mode" in self._options:
            connect_options["sslmode"] = self._options["ssl_mode"]

        if "ssl_cert" in self._options:
            connect_options["sslcert"] = self._options["ssl_cert"]

        if "ssl_key" in self._options:
            connect_options["sslkey"] = self._options["ssl_key"]

        if "ssl_root_cert" in self._options:
            connect_options["sslrootcert"] = self._options["ssl_root_cert"]

        if "ssl_crl" in self._options:
            connect_options["sslcrl"] = self._options["ssl_crl"]

        if "client_encoding" in self._options:
            connect_options["client_encoding"] = self._options["client_encoding"]

        search_path = self._options.get("search_path")
        if search_path:
            connect_options["options"] = f"-c search_path={search_path}"

        # The slot is claimed before the handle is opened -- opening first and
        # counting after is exactly what the limit exists to prevent.
        with self._connections.reserve():
            self._connections.set(psycopg.connect(**connect_options))
            self._closed = False

        self._exec_startup_queries()

    def _disconnect(self) -> None:
        connection = self._connections.discard()
        if connection is not None:
            connection.close()

    def is_connected(self) -> bool:
        import psycopg

        connection = self._connections.current()
        if connection is None or connection.closed:
            return False

        try:
            connection.execute("SELECT 1")
        except psycopg.Error:
            return False
        return True

    def version(self) -> str:
        import psycopg

        try:
            cursor = self._connection.execute("SELECT version()")
            row = cursor.fetchone()
            if row:
                match = _VERSION_PATTERN.search(str(row[0]))
                if match:
                    return match.group(1)
            return "0"
        except psycopg.Error:
            return "0"

    def _encode(self, query: str) -> bytes:
        return query.encode(self._connection.info.encoding)

    def exec(self, query: str) -> None:
        start = time.time()
        error: str | None = None
        try:
            self._connection.execute(self._encode(query))
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
            cursor = self._connection.execute(self._encode(query))
            return PsycopgResult(cursor)
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
            if emulate_prepare:
                sql_full = query_with_params.to_sql(dialect)
                cursor = self._connection.execute(self._encode(sql_full))
            else:
                cursor = self._connection.execute(self._encode(sql), params)
            return PsycopgResult(cursor)
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = time.time() - start
            self._debug(query_with_params.to_sql(dialect), duration, error)

    @property
    def in_transaction(self) -> bool:
        from psycopg.pq import TransactionStatus

        return bool(self._connection.info.transaction_status != TransactionStatus.IDLE)

    def last_insert_id(self, name: str | None = None) -> int | str | None:
        import psycopg

        try:
            if name:
                cursor = self._connection.execute("SELECT currval(%s::regclass)", (name,))
            else:
                cursor = self._connection.execute("SELECT lastval()")
            row = cursor.fetchone()
        except psycopg.Error:
            return None
        return row[0] if row else None

    def get_connection(self) -> Any:
        return self._connection

    def close(self) -> None:
        import psycopg

        for connection in self._connections.take_all():
            with contextlib.suppress(psycopg.Error):
                connection.close()

        self._closed = True


class AsyncpgAdapter(AdapterABC):
    """asyncpg driver behind the synchronous :class:`AdapterABC` surface.

    asyncpg is coroutine-only and binds a connection to the loop that created it,
    so this adapter owns a private event loop on a background thread and blocks
    on every call. That keeps it usable from synchronous code *and* from inside a
    running loop, where ``run_until_complete`` would raise.
    """

    def __init__(
        self,
        database_name: str,
        startup_queries: list[str] | None = None,
        options: dict[str, Any] | None = None,
        debug_callback: Callable[[str, float, str | None], None] | None = None,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        max_concurrent_connections: int | None = None,
        acquire_connection_timeout: float | None = None,
    ) -> None:
        super().__init__(
            driver_name="postgresql",
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
        self._loop_lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop
        self._loop_thread: threading.Thread
        self._start_loop()
        self._connections: ThreadLocalStore[AsyncpgConnection] = ThreadLocalStore(
            on_thread_exit=self._close_connection,
            max_values=max_concurrent_connections,
            acquire_timeout=acquire_connection_timeout,
        )
        self._connect()

    @property
    def _connection(self) -> AsyncpgConnection:
        connection = self._connections.current()
        if connection is not None:
            return connection

        self._ensure_not_closed()
        self._close_orphaned_connections()
        self._connect()
        return self._connections.require()

    def _close_connection(self, connection: AsyncpgConnection) -> None:
        """Hand the close to the loop thread without waiting on it.

        An asyncpg connection belongs to the event loop, not to the thread that
        ran queries through it, so the loop is the only place it can be shut
        down. Waiting on the result would stall the caller for a network round
        trip it gains nothing from -- and on the thread-exit path that caller is
        a thread already in teardown, which must not be parked on a cross-thread
        future that a wedged loop would never complete."""
        coroutine = connection.close()
        try:
            asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        except RuntimeError:
            # The loop is already gone, so the close can never be dispatched.
            # Closing the coroutine keeps it from warning about never being
            # awaited; the socket goes away with the loop.
            coroutine.close()

    def _close_orphaned_connections(self) -> None:
        for connection in self._connections.take_orphaned():
            self._close_connection(connection)

    def connection_count(self) -> int:
        return self._connections.count()

    def _start_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, name="flowlab-db-asyncpg", daemon=True)
        self._loop_thread.start()

    def _ensure_loop(self) -> None:
        with self._loop_lock:
            if self._loop.is_closed():
                self._start_loop()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _await(self, coroutine: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    def _ssl_option(self) -> ssl.SSLContext | str | None:
        ssl_mode = self._options.get("ssl_mode")
        ssl_cert = self._options.get("ssl_cert")
        ssl_key = self._options.get("ssl_key")
        ssl_root_cert = self._options.get("ssl_root_cert")
        ssl_crl = self._options.get("ssl_crl")

        if not ssl_cert and not ssl_key and not ssl_root_cert and not ssl_crl:
            return str(ssl_mode) if ssl_mode else None

        import ssl as ssl_module

        context = ssl_module.create_default_context(cafile=ssl_root_cert)

        if ssl_cert:
            context.load_cert_chain(ssl_cert, keyfile=ssl_key)

        if ssl_crl:
            context.load_verify_locations(cafile=ssl_crl)
            context.verify_flags |= ssl_module.VERIFY_CRL_CHECK_CHAIN

        if ssl_mode in ("disable", "allow", "prefer", "require"):
            context.check_hostname = False
            context.verify_mode = ssl_module.CERT_NONE
        elif ssl_mode == "verify-ca":
            context.check_hostname = False

        return context

    def _connect(self) -> None:
        self._ensure_loop()

        connect_options: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "database": self._database_name,
            "user": self._user,
            "password": self._password,
        }

        ssl_option = self._ssl_option()
        if ssl_option is not None:
            connect_options["ssl"] = ssl_option

        search_path = self._options.get("search_path")
        if search_path:
            connect_options["server_settings"] = {"search_path": search_path}

        # The slot is claimed before the handle is opened -- opening first and
        # counting after is exactly what the limit exists to prevent.
        with self._connections.reserve():
            self._connections.set(self._await(self._open(connect_options)))
            self._closed = False

        self._exec_startup_queries()

    async def _open(self, connect_options: dict[str, Any]) -> AsyncpgConnection:
        import asyncpg

        connection: AsyncpgConnection = await asyncpg.connect(**connect_options)

        for type_name in ("json", "jsonb"):
            await connection.set_type_codec(
                type_name,
                encoder=encode_json,
                decoder=decode_json,
                schema="pg_catalog",
                format="text",
            )

        return connection

    def _disconnect(self) -> None:
        connection = self._connections.discard()
        if connection is None or self._loop.is_closed():
            return
        self._await(connection.close())

    def is_connected(self) -> bool:
        connection = self._connections.current()
        if connection is None or self._loop.is_closed():
            return False
        return not connection.is_closed()

    def reconnect(self) -> None:
        # close() tears the loop down as well, so a reconnect after it has to
        # bring a new loop thread up before any coroutine can be awaited.
        self._ensure_loop()
        super().reconnect()

    async def _fetch(self, connection: AsyncpgConnection, query: str) -> AsyncpgResult:
        statement = await connection.prepare(query)
        records = await statement.fetch()
        return AsyncpgResult(statement.get_attributes(), records)

    async def _fetch_with_params(
        self,
        connection: AsyncpgConnection,
        dialect: DialectABC,
        query: str,
        params: list[Any],
    ) -> AsyncpgResult:
        statement = await connection.prepare(query)
        adapted = _adapt_params(dialect, statement.get_parameters(), params)
        records = await statement.fetch(*adapted)
        return AsyncpgResult(statement.get_attributes(), records)

    def version(self) -> str:
        import asyncpg

        try:
            row = self._await(self._connection.fetchrow("SELECT version()"))
            if row:
                match = _VERSION_PATTERN.search(str(row[0]))
                if match:
                    return match.group(1)
            return "0"
        except asyncpg.PostgresError:
            return "0"

    def exec(self, query: str) -> None:
        start = time.time()
        error: str | None = None
        try:
            self._await(self._connection.execute(query))
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
            return self._await(self._fetch(self._connection, query))
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
        sql = _placeholders_to_dollar_signs(query_with_params.query)
        params = [_cast_param(dialect, param) for param in query_with_params.params]

        start = time.time()
        error: str | None = None
        try:
            connection = self._connection
            if emulate_prepare:
                return self._await(self._fetch(connection, query_with_params.to_sql(dialect)))
            return self._await(self._fetch_with_params(connection, dialect, sql, params))
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = time.time() - start
            self._debug(query_with_params.to_sql(dialect), duration, error)

    @property
    def in_transaction(self) -> bool:
        return bool(self._connection.is_in_transaction())

    def last_insert_id(self, name: str | None = None) -> int | str | None:
        import asyncpg

        try:
            if name:
                row = self._await(self._connection.fetchrow("SELECT currval($1::regclass)", name))
            else:
                row = self._await(self._connection.fetchrow("SELECT lastval()"))
        except asyncpg.PostgresError:
            return None
        return row[0] if row else None

    def get_connection(self) -> Any:
        return self._connection

    def close(self) -> None:
        with self._loop_lock:
            if self._loop.is_closed():
                return

            try:
                for connection in self._connections.take_all():
                    with contextlib.suppress(Exception):
                        self._await(connection.close())
            finally:
                self._closed = True
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._loop_thread.join()
                self._loop.close()
