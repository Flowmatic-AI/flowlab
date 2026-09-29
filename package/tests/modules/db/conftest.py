from __future__ import annotations

import pytest

from flowlab.modules.db.database import DatabaseABC
from flowlab.modules.db.dialects import MySQLDialect, PostgresqlDialect, SQLDialect, SQLiteDialect


class _MockDatabase(DatabaseABC):
    """Minimal database stub for unit tests that don't execute queries."""

    def __init__(self) -> None:
        pass


@pytest.fixture
def mock_db() -> _MockDatabase:
    """Return a mock database for unit tests that only call to_query_with_params()."""
    return _MockDatabase()


@pytest.fixture
def sql_dialect() -> SQLDialect:
    """Return a base ANSI SQL dialect."""
    return SQLDialect()


@pytest.fixture
def sqlite_dialect() -> SQLiteDialect:
    """Return a SQLite dialect."""
    return SQLiteDialect()


@pytest.fixture
def pg_dialect() -> PostgresqlDialect:
    """Return a PostgreSQL dialect."""
    return PostgresqlDialect()


@pytest.fixture
def mysql_dialect() -> MySQLDialect:
    """Return a MySQL dialect."""
    return MySQLDialect()
