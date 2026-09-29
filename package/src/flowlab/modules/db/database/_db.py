from __future__ import annotations

from collections.abc import Callable
from typing import Any, Self

from flowlab.modules.db.database._abc import DatabaseABC


class DB(DatabaseABC):
    @classmethod
    def connect_sqlite(
        cls,
        name: str,
        startup_queries: list[str] | None = None,
        options: dict[str, Any] | None = None,
        debug_callback: Callable[[str, float, str | None], None] | None = None,
        ensure_always_connected: bool = False,
        max_concurrent_connections: int | None = None,
        acquire_connection_timeout: float | None = None,
    ) -> Self:
        from flowlab.modules.db.adapters import SQLiteAdapter
        from flowlab.modules.db.dialects import SQLiteDialect

        adapter = SQLiteAdapter(
            database_name=name,
            startup_queries=startup_queries,
            options=options,
            debug_callback=debug_callback,
            max_concurrent_connections=max_concurrent_connections,
            acquire_connection_timeout=acquire_connection_timeout,
        )
        return cls(adapter, SQLiteDialect(version=adapter.version(), options=options or {}), ensure_always_connected)

    @classmethod
    def connect_postgresql(
        cls,
        name: str,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        startup_queries: list[str] | None = None,
        options: dict[str, Any] | None = None,
        debug_callback: Callable[[str, float, str | None], None] | None = None,
        asyncpg_adapter: bool = True,
        ensure_always_connected: bool = False,
        max_concurrent_connections: int | None = None,
        acquire_connection_timeout: float | None = None,
    ) -> Self:
        from flowlab.modules.db.adapters import AdapterABC, AsyncpgAdapter, PsycopgAdapter
        from flowlab.modules.db.dialects import PostgresqlDialect

        adapter: AdapterABC
        if asyncpg_adapter:
            adapter = AsyncpgAdapter(
                database_name=name,
                host=host,
                port=port,
                user=user,
                password=password,
                startup_queries=startup_queries,
                options=options,
                debug_callback=debug_callback,
                max_concurrent_connections=max_concurrent_connections,
                acquire_connection_timeout=acquire_connection_timeout,
            )
        else:
            adapter = PsycopgAdapter(
                database_name=name,
                host=host,
                port=port,
                user=user,
                password=password,
                startup_queries=startup_queries,
                options=options,
                debug_callback=debug_callback,
                max_concurrent_connections=max_concurrent_connections,
                acquire_connection_timeout=acquire_connection_timeout,
            )
        return cls(
            adapter,
            PostgresqlDialect(version=adapter.version(), options=options or {}),
            ensure_always_connected,
        )

    @classmethod
    def _connect_mysql_family(
        cls,
        name: str,
        host: str,
        port: int,
        user: str,
        password: str,
        startup_queries: list[str] | None,
        options: dict[str, Any] | None,
        debug_callback: Callable[[str, float, str | None], None] | None,
        is_mariadb: bool,
        ensure_always_connected: bool,
        max_concurrent_connections: int | None,
        acquire_connection_timeout: float | None,
    ) -> Self:
        from flowlab.modules.db.adapters import MySQLAdapter
        from flowlab.modules.db.dialects import MySQLDialect

        adapter = MySQLAdapter(
            database_name=name,
            host=host,
            port=port,
            user=user,
            password=password,
            startup_queries=startup_queries,
            options=options,
            debug_callback=debug_callback,
            max_concurrent_connections=max_concurrent_connections,
            acquire_connection_timeout=acquire_connection_timeout,
        )
        return cls(
            adapter,
            MySQLDialect(version=adapter.version(), options=options or {}, is_mariadb=is_mariadb),
            ensure_always_connected,
        )

    @classmethod
    def connect_mysql(
        cls,
        name: str,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        startup_queries: list[str] | None = None,
        options: dict[str, Any] | None = None,
        debug_callback: Callable[[str, float, str | None], None] | None = None,
        ensure_always_connected: bool = False,
        max_concurrent_connections: int | None = None,
        acquire_connection_timeout: float | None = None,
    ) -> Self:
        return cls._connect_mysql_family(
            name,
            host,
            port,
            user,
            password,
            startup_queries,
            options,
            debug_callback,
            is_mariadb=False,
            ensure_always_connected=ensure_always_connected,
            max_concurrent_connections=max_concurrent_connections,
            acquire_connection_timeout=acquire_connection_timeout,
        )

    @classmethod
    def connect_mariadb(
        cls,
        name: str,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        startup_queries: list[str] | None = None,
        options: dict[str, Any] | None = None,
        debug_callback: Callable[[str, float, str | None], None] | None = None,
        ensure_always_connected: bool = False,
        max_concurrent_connections: int | None = None,
        acquire_connection_timeout: float | None = None,
    ) -> Self:
        return cls._connect_mysql_family(
            name,
            host,
            port,
            user,
            password,
            startup_queries,
            options,
            debug_callback,
            is_mariadb=True,
            ensure_always_connected=ensure_always_connected,
            max_concurrent_connections=max_concurrent_connections,
            acquire_connection_timeout=acquire_connection_timeout,
        )

    @staticmethod
    def drivers() -> list[str]:
        import importlib.util

        drivers: list[str] = []

        if importlib.util.find_spec("sqlite3") is not None:
            drivers.append("sqlite")

        if importlib.util.find_spec("psycopg") is not None or importlib.util.find_spec("asyncpg") is not None:
            drivers.append("postgresql")

        # The parent has to be checked first: looking a submodule up imports its
        # package, and find_spec() raises rather than answering None when that
        # package is not installed at all.
        if importlib.util.find_spec("mysql") is not None and importlib.util.find_spec("mysql.connector") is not None:
            drivers.append("mysql")
            drivers.append("mariadb")

        return drivers
