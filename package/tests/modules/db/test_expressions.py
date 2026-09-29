from __future__ import annotations

from flowlab.modules.db.dialects import SQLDialect
from flowlab.modules.db.query.expressions import Alias, CurrentTimestamp, Expression, Identifier, Raw


def test_raw_expression(sql_dialect: SQLDialect) -> None:
    raw = Raw("NOW()")
    assert raw.sql(sql_dialect) == "NOW()"
    assert raw.params(sql_dialect) == []
    assert raw.raw_sql(sql_dialect) == "NOW()"


def test_identifier(sql_dialect: SQLDialect) -> None:
    ident = Identifier("column_name")
    assert ident.sql(sql_dialect) == '"column_name"'


def test_identifier_list(sql_dialect: SQLDialect) -> None:
    ident = Identifier(["schema", "table"])
    assert ident.sql(sql_dialect) == '"schema"."table"'


def test_alias(sql_dialect: SQLDialect) -> None:
    alias = Alias("u", "users")
    result: str = alias.sql(sql_dialect)
    assert '"u"' in result
    assert '"users"' in result
    assert "AS" in result


def test_alias_with_identifier(sql_dialect: SQLDialect) -> None:
    alias = Alias(["public", "users"], "u")
    result: str = alias.sql(sql_dialect)
    assert "AS" in result


def test_expression(sql_dialect: SQLDialect) -> None:
    expr = Expression("? + ?", [1, 2])
    assert expr.sql(sql_dialect) == "? + ?"
    assert expr.params(sql_dialect) == [1, 2]


def test_expression_raw(sql_dialect: SQLDialect) -> None:
    expr = Expression("? + ?", [1, 2])
    raw: str = expr.raw_sql(sql_dialect)
    assert "1" in raw
    assert "2" in raw
    assert "+" in raw


def test_current_timestamp(sql_dialect: SQLDialect) -> None:
    ct = CurrentTimestamp()
    assert ct.sql(sql_dialect) == "CURRENT_TIMESTAMP"
    assert ct.params(sql_dialect) == []
    assert ct.raw_sql(sql_dialect) == "CURRENT_TIMESTAMP"


def test_expression_empty_params(sql_dialect: SQLDialect) -> None:
    expr = Expression("NOW()")
    assert expr.sql(sql_dialect) == "NOW()"
    assert expr.params(sql_dialect) == []
