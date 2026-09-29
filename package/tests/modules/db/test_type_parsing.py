"""Tests for ``parse_type()`` — the inverse of ``DialectABC.type()``.

``describe_table()`` reads a declared type back off the server, so what the
dialect renders and what it parses have to be the same mapping walked in
opposite directions.
"""

from __future__ import annotations

import sys

import pytest

from flowlab.modules.db.dialects import DialectABC, MySQLDialect, PostgresqlDialect, SQLDialect, SQLiteDialect
from flowlab.modules.db.query.enums import TypeEnum

WIDTHS = [None, 6, 16, 32, 64, 255, 256, 65535, 65536, 16777215, 16777216, sys.maxsize]


def _dialects() -> list[DialectABC]:
    return [SQLDialect(), PostgresqlDialect(version="18"), MySQLDialect(version="8.0.36"), SQLiteDialect()]


@pytest.mark.parametrize("dialect", _dialects(), ids=lambda d: type(d).__name__)
def test_parse_type_round_trips_everything_the_dialect_renders(dialect: DialectABC) -> None:
    """Re-rendering a parsed type reproduces the string it was parsed from."""
    for type_enum in TypeEnum:
        for width in WIDTHS:
            rendered = dialect.type(type_enum, width)
            parsed_type, parsed_size = dialect.parse_type(rendered)

            assert isinstance(parsed_type, TypeEnum), rendered
            assert dialect.type(parsed_type, parsed_size) == rendered


@pytest.mark.parametrize("dialect", _dialects(), ids=lambda d: type(d).__name__)
def test_parse_type_recovers_the_type_enum(dialect: DialectABC) -> None:
    """A rendered type parses back to the TypeEnum it came from.

    BOOL is exempt on the base dialect alone: it has no boolean type, so it
    renders one as INTEGER and nothing distinguishes it from an INT.
    """
    for type_enum in TypeEnum:
        if type_enum == TypeEnum.BOOL and not dialect.bool:
            continue

        for width in WIDTHS:
            assert dialect.parse_type(dialect.type(type_enum, width))[0] == type_enum


def test_parse_type_widths(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.parse_type("VARCHAR(255)") == (TypeEnum.STRING, 255)
    assert sql_dialect.parse_type("BIGINT") == (TypeEnum.INT, 64)
    assert sql_dialect.parse_type("INTEGER") == (TypeEnum.INT, 32)
    assert sql_dialect.parse_type("SMALLINT") == (TypeEnum.INT, 16)
    assert sql_dialect.parse_type("TEXT") == (TypeEnum.STRING, sys.maxsize)
    assert sql_dialect.parse_type("DECIMAL(30, 15)") == (TypeEnum.FLOAT, 64)
    assert sql_dialect.parse_type("DECIMAL(15, 7)") == (TypeEnum.FLOAT, 32)
    assert sql_dialect.parse_type("DATETIME") == (TypeEnum.DATETIME, None)
    assert sql_dialect.parse_type("JSON") == (TypeEnum.JSON, None)


def test_parse_type_is_case_and_space_insensitive(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.parse_type("varchar(64)") == (TypeEnum.STRING, 64)
    assert sql_dialect.parse_type("  VarChar ( 64 )  ") == (TypeEnum.STRING, 64)


def test_parse_type_keeps_an_unknown_type_as_a_string(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.parse_type("geometry") == ("geometry", None)
    assert sql_dialect.parse_type("enum('a','b')") == ("enum('a','b')", None)
    assert sql_dialect.parse_type("USER-DEFINED") == ("USER-DEFINED", None)


def test_pg_parses_what_format_type_reports(pg_dialect: PostgresqlDialect) -> None:
    # format_type() spells names out in full and in lower case.
    assert pg_dialect.parse_type("character varying(64)") == (TypeEnum.STRING, 64)
    assert pg_dialect.parse_type("character varying") == (TypeEnum.STRING, sys.maxsize)
    assert pg_dialect.parse_type("timestamp with time zone") == (TypeEnum.DATETIME, None)
    assert pg_dialect.parse_type("double precision") == (TypeEnum.FLOAT, 64)
    assert pg_dialect.parse_type("real") == (TypeEnum.FLOAT, 32)
    assert pg_dialect.parse_type("boolean") == (TypeEnum.BOOL, None)
    assert pg_dialect.parse_type("bigint") == (TypeEnum.INT, 64)
    assert pg_dialect.parse_type("jsonb") == (TypeEnum.JSON, None)


def test_mysql_parses_what_column_type_reports(mysql_dialect: MySQLDialect) -> None:
    assert mysql_dialect.parse_type("varchar(64)") == (TypeEnum.STRING, 64)
    assert mysql_dialect.parse_type("int") == (TypeEnum.INT, 32)
    assert mysql_dialect.parse_type("bigint") == (TypeEnum.INT, 64)
    assert mysql_dialect.parse_type("datetime(6)") == (TypeEnum.DATETIME, 6)
    assert mysql_dialect.parse_type("double") == (TypeEnum.FLOAT, 64)
    assert mysql_dialect.parse_type("json") == (TypeEnum.JSON, None)

    # Each MySQL text type is bounded, so its width is that bound. None of them
    # reaches sys.maxsize, which stands for a genuinely unbounded TEXT.
    assert mysql_dialect.parse_type("text") == (TypeEnum.STRING, 65535)
    assert mysql_dialect.parse_type("mediumtext") == (TypeEnum.STRING, 16777215)
    assert mysql_dialect.parse_type("longtext") == (TypeEnum.STRING, 4294967295)

    # COLUMN_TYPE carries the attributes along.
    assert mysql_dialect.parse_type("bigint unsigned") == (TypeEnum.INT, 64)


def test_mysql_reads_tinyint_as_a_boolean(mysql_dialect: MySQLDialect) -> None:
    # MySQL has no boolean, so TINYINT is what this dialect renders one as.
    assert mysql_dialect.parse_type("tinyint") == (TypeEnum.BOOL, None)
    assert mysql_dialect.parse_type("tinyint(1)") == (TypeEnum.BOOL, None)


def test_sqlite_reads_real_at_the_builders_default_width(sqlite_dialect: SQLiteDialect) -> None:
    # SQLite renders every float as REAL, so the string carries no width.
    assert sqlite_dialect.parse_type("REAL") == (TypeEnum.FLOAT, 64)


def test_sqlite_identity_column_is_64_bit(sqlite_dialect: SQLiteDialect) -> None:
    # An identity column is always INTEGER PRIMARY KEY AUTOINCREMENT whatever
    # its declared width, and that rowid alias is a 64-bit integer.
    assert sqlite_dialect.parse_column_type("INTEGER", auto_increment=True) == (TypeEnum.INT, 64)
    assert sqlite_dialect.parse_column_type("INTEGER", auto_increment=False) == (TypeEnum.INT, 32)


def test_parse_column_type_defaults_to_parse_type(pg_dialect: PostgresqlDialect) -> None:
    # PostgreSQL keeps the width on a serial (integer vs bigint), so it has no
    # reason to override the auto-increment hook.
    assert pg_dialect.parse_column_type("integer", auto_increment=True) == (TypeEnum.INT, 32)
    assert pg_dialect.parse_column_type("bigint", auto_increment=True) == (TypeEnum.INT, 64)
