"""Unit tests for datetime and JSON serialization across the dialects.

The driver-facing halves of this (asyncpg codecs, sqlite3 converters, MySQL
result decoding) are covered by the integration modules; what is checked here is
the dialect-level contract every adapter builds on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from flowlab.modules.db.database import DatabaseABC
from flowlab.modules.db.dialects import MySQLDialect, PostgresqlDialect, SQLDialect, SQLiteDialect
from flowlab.modules.db.query.enums import TypeEnum
from flowlab.modules.db.query.expressions import PostgresArray


def test_cast_json_serializes_documents(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.cast_json({"k": "v", "n": [1, 2]}) == '{"k": "v", "n": [1, 2]}'
    assert sql_dialect.cast_json([1, "a", None, True]) == '[1, "a", null, true]'
    assert sql_dialect.cast_json({}) == "{}"


def test_cast_json_renders_nested_values_json_does_not_know(sql_dialect: SQLDialect) -> None:
    """Temporals become ISO-8601 and decimals strings, so a document holding
    them survives the round trip instead of raising."""
    document = {"at": datetime(2026, 8, 3, 12, 30, 45, tzinfo=UTC), "amount": Decimal("1.10")}
    assert sql_dialect.cast_json(document) == '{"at": "2026-08-03T12:30:45+00:00", "amount": "1.10"}'


def test_parse_json_decodes_text_and_bytes(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.parse_json('{"k": "v"}') == {"k": "v"}
    assert sql_dialect.parse_json(b"[1, 2]") == [1, 2]
    assert sql_dialect.parse_json(bytearray(b'"s"')) == "s"


def test_parse_json_passes_through_what_it_cannot_decode(sql_dialect: SQLDialect) -> None:
    """A driver that already decoded the column, or a column holding non-JSON
    text, must not blow up the fetch."""
    assert sql_dialect.parse_json({"already": "decoded"}) == {"already": "decoded"}
    assert sql_dialect.parse_json("not json at all") == "not json at all"
    assert sql_dialect.parse_json(None) is None


def test_cast_to_driver_serializes_documents(sql_dialect: SQLDialect, mysql_dialect: MySQLDialect) -> None:
    assert sql_dialect.cast_to_driver({"k": "v"}) == '{"k": "v"}'
    assert sql_dialect.cast_to_driver([1, 2]) == "[1, 2]"
    assert mysql_dialect.cast_to_driver({"k": "v"}) == '{"k": "v"}'
    assert mysql_dialect.cast_to_driver([1, 2]) == "[1, 2]"


def test_postgres_cast_to_driver_treats_bare_lists_as_json(pg_dialect: PostgresqlDialect) -> None:
    """PostgreSQL has an array type as well, but nothing in a list says which is
    meant -- so a bare list is a document here too."""
    assert pg_dialect.cast_to_driver({"k": "v"}) == '{"k": "v"}'
    assert pg_dialect.cast_to_driver(["a", "b"]) == '["a", "b"]'


def test_postgres_array_unwraps_for_the_driver(pg_dialect: PostgresqlDialect) -> None:
    """PostgresArray is handed to the driver as a plain list, which psycopg and
    asyncpg both bind as an array. Element types are left alone so the driver
    types them natively."""
    happened_at = datetime(2026, 8, 3, 12, 30, 45, tzinfo=UTC)
    assert pg_dialect.cast_to_driver(PostgresArray(["a", "b"])) == ["a", "b"]
    assert pg_dialect.cast_to_driver(PostgresArray([happened_at])) == [happened_at]
    assert pg_dialect.cast_to_driver(PostgresArray([])) == []


def test_postgres_array_falls_back_to_json_without_an_array_type(
    sql_dialect: SQLDialect, sqlite_dialect: SQLiteDialect, mysql_dialect: MySQLDialect
) -> None:
    """A query written for PostgreSQL still runs elsewhere: engines with no
    array type drop the array reading and store the values as JSON."""
    for dialect in (sql_dialect, sqlite_dialect, mysql_dialect):
        assert dialect.cast_to_driver(PostgresArray([1, 2])) == "[1, 2]"

    assert sql_dialect.cast_to_query(PostgresArray([1, 2])) == "'[1, 2]'"
    assert sqlite_dialect.cast_to_query(PostgresArray([1, 2])) == "'[1, 2]'"
    assert mysql_dialect.cast_to_query(PostgresArray([1, 2])) == '"[1, 2]"'


def test_cast_to_query_inlines_documents(sql_dialect: SQLDialect, sqlite_dialect: SQLiteDialect) -> None:
    """emulate_prepare renders params into the SQL, so documents need a literal."""
    assert sql_dialect.cast_to_query({"k": "v"}) == '\'{"k": "v"}\''
    assert sqlite_dialect.cast_to_query([1, 2]) == "'[1, 2]'"


def test_postgres_cast_to_query_inlines_arrays_and_documents_differently(
    pg_dialect: PostgresqlDialect,
) -> None:
    assert pg_dialect.cast_to_query(PostgresArray(["a", "b"])) == "ARRAY['a', 'b']"
    assert pg_dialect.cast_to_query(PostgresArray([1, 2])) == "ARRAY[1, 2]"
    assert pg_dialect.cast_to_query(PostgresArray([])) == "'{}'"
    assert pg_dialect.cast_to_query(["a", "b"]) == '\'["a", "b"]\''
    assert pg_dialect.cast_to_query({"k": "v"}) == '\'{"k": "v"}\''


def test_json_type_per_dialect(
    sql_dialect: SQLDialect,
    sqlite_dialect: SQLiteDialect,
    pg_dialect: PostgresqlDialect,
    mysql_dialect: MySQLDialect,
) -> None:
    assert sql_dialect.type(TypeEnum.JSON) == "JSON"
    assert sqlite_dialect.type(TypeEnum.JSON) == "JSON"
    assert pg_dialect.type(TypeEnum.JSON) == "JSONB"
    assert mysql_dialect.type(TypeEnum.JSON) == "JSON"


def test_create_table_json_column_builder(
    mock_db: DatabaseABC,
    sqlite_dialect: SQLiteDialect,
    pg_dialect: PostgresqlDialect,
    mysql_dialect: MySQLDialect,
) -> None:
    from flowlab.modules.db.query import CreateTableQuery

    for dialect, expected in (
        (sqlite_dialect, '"payload" JSON'),
        (pg_dialect, '"payload" JSONB NOT NULL'),
        (mysql_dialect, "`payload` JSON"),
    ):
        query = CreateTableQuery(dialect, "docs", mock_db)
        query.json("payload", not_null=dialect is pg_dialect)
        assert expected in query.to_query_with_params().query


def test_json_type_falls_back_to_text_on_servers_without_it() -> None:
    assert PostgresqlDialect(version="9.3").type(TypeEnum.JSON) == "JSON"
    assert PostgresqlDialect(version="9.1").type(TypeEnum.JSON) == "TEXT"
    assert MySQLDialect(version="5.6").type(TypeEnum.JSON) == "TEXT"
    assert MySQLDialect(version="10.1", is_mariadb=True).type(TypeEnum.JSON) == "TEXT"
    assert MySQLDialect(version="10.3", is_mariadb=True).type(TypeEnum.JSON) == "JSON"
