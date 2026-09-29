"""Tests for ``parse_default()`` — the inverse of ``_build_column_default()``.

``describe_table()`` reads a DEFAULT clause back off the server as the text the
engine stored, and reports the Python value the column was declared with. The
three engines store that text differently: PostgreSQL hangs a ``::type`` cast
off the literal, MySQL reports the value with no quotes at all.
"""

from __future__ import annotations

from datetime import datetime

from flowlab.modules.db.dialects import MySQLDialect, PostgresqlDialect, SQLDialect, SQLiteDialect
from flowlab.modules.db.query.enums import TypeEnum
from flowlab.modules.db.query.expressions import CurrentTimestamp


def test_parse_default_reads_literals_as_python_values(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.parse_default("1", TypeEnum.BOOL) is True
    assert sql_dialect.parse_default("0", TypeEnum.BOOL) is False
    assert sql_dialect.parse_default("true", TypeEnum.BOOL) is True
    assert sql_dialect.parse_default("false", TypeEnum.BOOL) is False
    assert sql_dialect.parse_default("42", TypeEnum.INT) == 42
    assert sql_dialect.parse_default("1.5", TypeEnum.FLOAT) == 1.5
    assert sql_dialect.parse_default("'no way'", TypeEnum.STRING) == "no way"
    assert sql_dialect.parse_default("'{\"a\": 1}'", TypeEnum.JSON) == {"a": 1}


def test_parse_default_undoubles_an_escaped_quote(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.parse_default("'it''s here'", TypeEnum.STRING) == "it's here"
    assert sql_dialect.parse_default("''", TypeEnum.STRING) == ""


def test_parse_default_reads_a_datetime_literal(sql_dialect: SQLDialect) -> None:
    parsed = sql_dialect.parse_default("'2020-01-01 12:30:00'", TypeEnum.DATETIME)

    assert isinstance(parsed, datetime)
    assert (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute) == (2020, 1, 1, 12, 30)


def test_parse_default_recognises_current_timestamp(sql_dialect: SQLDialect, mysql_dialect: MySQLDialect) -> None:
    """The expression the builder took comes back, so a described column re-creates.

    MySQL carries the fractional precision along, and NOW() is the same function
    spelled differently.
    """
    assert isinstance(sql_dialect.parse_default("CURRENT_TIMESTAMP", TypeEnum.DATETIME), CurrentTimestamp)
    assert isinstance(mysql_dialect.parse_default("CURRENT_TIMESTAMP(6)", TypeEnum.DATETIME), CurrentTimestamp)
    assert isinstance(sql_dialect.parse_default("now()", TypeEnum.DATETIME), CurrentTimestamp)


def test_parse_default_keeps_an_expression_as_a_string(sql_dialect: SQLDialect) -> None:
    """A default that is not a literal of its type is left exactly as reported."""
    assert sql_dialect.parse_default("(1 + 1)", TypeEnum.INT) == "(1 + 1)"
    assert sql_dialect.parse_default("upper('x')", TypeEnum.STRING) == "upper('x')"
    assert sql_dialect.parse_default("some_func()", TypeEnum.BOOL) == "some_func()"
    assert sql_dialect.parse_default("nan_or_not", TypeEnum.FLOAT) == "nan_or_not"


def test_parse_default_leaves_an_unknown_type_alone(sql_dialect: SQLDialect) -> None:
    """Without a TypeEnum there is no telling how to read the literal."""
    assert sql_dialect.parse_default("'whatever'", "VECTOR") == "'whatever'"


def test_sqlite_parses_the_literals_it_stores(sqlite_dialect: SQLiteDialect) -> None:
    assert sqlite_dialect.parse_default("'no way'", TypeEnum.STRING) == "no way"
    assert sqlite_dialect.parse_default("0", TypeEnum.BOOL) is False


def test_pg_strips_the_cast_it_appends(pg_dialect: PostgresqlDialect) -> None:
    assert pg_dialect.parse_default("'no way'::character varying", TypeEnum.STRING) == "no way"
    assert pg_dialect.parse_default("'it''s here'::character varying", TypeEnum.STRING) == "it's here"
    assert pg_dialect.parse_default("''::character varying", TypeEnum.STRING) == ""
    assert pg_dialect.parse_default("'{\"a\": 1}'::jsonb", TypeEnum.JSON) == {"a": 1}
    assert pg_dialect.parse_default("'long one'::text", TypeEnum.STRING) == "long one"
    assert pg_dialect.parse_default("false", TypeEnum.BOOL) is False


def test_mysql_reports_the_value_rather_than_the_literal(mysql_dialect: MySQLDialect) -> None:
    """MySQL stores `no way`, not `'no way'`, so there are no quotes to strip."""
    assert mysql_dialect.parse_default("no way", TypeEnum.STRING) == "no way"
    assert mysql_dialect.parse_default("it's here", TypeEnum.STRING) == "it's here"
    assert mysql_dialect.parse_default("", TypeEnum.STRING) == ""
    assert mysql_dialect.parse_default("1", TypeEnum.BOOL) is True
    assert mysql_dialect.parse_default("42", TypeEnum.INT) == 42
