"""Regression tests for hand-port bugs fixed in the SQLDialect base class
(src/flowlab/modules/db/dialects/_sql_dialect.py, src/flowlab/modules/db/dialects/_base.py).

Each test below corresponds to a specific behavioral divergence from the PHP
original (Database/Dialects/SQLDialect.php) that was found and fixed.
"""

from __future__ import annotations

import pytest

from flowlab.modules.db import QueryError, QueryWithParams
from flowlab.modules.db.dialects import SQLDialect
from flowlab.modules.db.query import Condition, OnConflict, SelectQuery, Union
from flowlab.modules.db.query.enums import ConditionEnum, TypeEnum, UnionEnum
from flowlab.modules.db.query.expressions import Excluded


def test_union_always_wraps_base_select_in_parens(sql_dialect: SQLDialect, mock_db) -> None:
    """PHP's buildUnions() always wraps the base SELECT in parentheses when
    any UNION is present, regardless of LIMIT/OFFSET -- not just when a
    LIMIT/OFFSET happens to also be present."""
    other = SelectQuery(sql_dialect, "t2", database=mock_db)
    other.columns(["name"])

    qwp: QueryWithParams = sql_dialect.select(
        distinct=None,
        columns=["name"],
        table="t1",
        joins=None,
        where=None,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=[Union(union=UnionEnum.UNION, select_query=other)],
    )
    assert qwp.query.startswith("(SELECT")
    assert ") UNION (SELECT" in qwp.query


def test_insert_column_list_is_union_across_all_rows(sql_dialect: SQLDialect) -> None:
    """The column list must be the union of keys across *every* row, not
    just the first row's keys."""
    qwp = sql_dialect.insert(
        table="t",
        values=[{"a": 1}, {"a": 2, "b": 3}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    assert '"a", "b"' in qwp.query


def test_insert_missing_column_uses_literal_default(sql_dialect: SQLDialect) -> None:
    """A row that omits a column present in another row gets the literal
    (unbound) DEFAULT keyword, not a bound NULL parameter."""
    qwp = sql_dialect.insert(
        table="t",
        values=[{"a": 1, "b": 2}, {"a": 3}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    assert "(?, ?), (?, DEFAULT)" in qwp.query
    assert qwp.params == [1, 2, 3]
    assert None not in qwp.params


def test_create_table_requires_at_least_one_column(sql_dialect: SQLDialect) -> None:
    with pytest.raises(QueryError):
        sql_dialect.create_table(
            if_not_exists=False,
            table="t",
            columns=[],
            primary_keys=None,
            constraints=None,
        )


def test_update_requires_at_least_one_column(sql_dialect: SQLDialect) -> None:
    with pytest.raises(QueryError):
        sql_dialect.update(table="t", updates={}, where=None, returning=None)


def test_alter_table_requires_at_least_one_alter(sql_dialect: SQLDialect) -> None:
    with pytest.raises(QueryError):
        sql_dialect.alter_table(table="t", alters=[])


def test_on_conflict_excluded_columns_union_across_all_rows(sql_dialect: SQLDialect) -> None:
    sql_dialect.on_conflict = True
    qwp = sql_dialect.insert(
        table="t",
        values=[{"id": 1, "a": 2}, {"id": 3, "b": 4}],
        on_conflict=OnConflict(conflict=["id"], updates={}),
        returning=None,
        last_insert_id=None,
    )
    assert '"id" = EXCLUDED."id"' in qwp.query
    assert '"a" = EXCLUDED."a"' in qwp.query
    assert '"b" = EXCLUDED."b"' in qwp.query


def test_on_conflict_explicit_excluded_marker(sql_dialect: SQLDialect) -> None:
    sql_dialect.on_conflict = True
    qwp = sql_dialect.insert(
        table="t",
        values=[{"id": 1, "name": "a"}],
        on_conflict=OnConflict(conflict=["id"], updates={"name": Excluded()}),
        returning=None,
        last_insert_id=None,
    )
    assert 'DO UPDATE SET "name" = EXCLUDED."name"' in qwp.query


def test_empty_in_list_is_false_literal(sql_dialect: SQLDialect) -> None:
    """An empty IN-list must render as the bare literal `1 = 0` (always
    false), not `col IN (NULL)` -- which is NULL/unknown, not a clean false,
    under three-valued SQL logic."""
    where = [Condition(condition=ConditionEnum.IN, identifier="id", value=[])]
    qwp = sql_dialect.select(
        distinct=None,
        columns=None,
        table="t",
        joins=None,
        where=where,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert "1 = 0" in qwp.query
    assert "IN" not in qwp.query.split("WHERE")[1]


def test_empty_not_in_list_is_true_literal(sql_dialect: SQLDialect) -> None:
    where = [Condition(condition=ConditionEnum.NOT_IN, identifier="id", value=[])]
    qwp = sql_dialect.select(
        distinct=None,
        columns=None,
        table="t",
        joins=None,
        where=where,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert "1 = 1" in qwp.query


def test_in_with_subquery(sql_dialect: SQLDialect, mock_db) -> None:
    subquery = SelectQuery(sql_dialect, "other", database=mock_db)
    subquery.columns(["id"])
    where = [Condition(condition=ConditionEnum.IN, identifier="id", value=subquery)]
    qwp = sql_dialect.select(
        distinct=None,
        columns=None,
        table="t",
        joins=None,
        where=where,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert 'IN (SELECT "id" FROM "other")' in qwp.query


def test_glob_condition_translates_to_like(sql_dialect: SQLDialect) -> None:
    """Base ANSI SQL has no native GLOB; SQLDialect::buildConditionGlob
    translates the glob pattern to a LIKE pattern instead of raising."""
    where = [Condition(condition=ConditionEnum.GLOB, identifier="name", value="foo*b?r")]
    qwp = sql_dialect.select(
        distinct=None,
        columns=None,
        table="t",
        joins=None,
        where=where,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert "LIKE" in qwp.query
    assert "foo%b_r" in qwp.params


def test_regex_condition_builds_regexp_like_call(sql_dialect: SQLDialect) -> None:
    """regexp_like() must be called with identifier, pattern AND flags as
    three separate arguments -- not a single malformed placeholder."""
    where = [Condition(condition=ConditionEnum.REGEX, identifier="name", value="^A", flags="i")]
    qwp = sql_dialect.select(
        distinct=None,
        columns=None,
        table="t",
        joins=None,
        where=where,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert 'regexp_like("name", ?, ?)' in qwp.query
    assert qwp.params == ["^A", "i"]


def test_not_regex_condition(sql_dialect: SQLDialect) -> None:
    where = [Condition(condition=ConditionEnum.NOT_REGEX, identifier="name", value="^A")]
    qwp = sql_dialect.select(
        distinct=None,
        columns=None,
        table="t",
        joins=None,
        where=where,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert 'NOT regexp_like("name", ?, ?)' in qwp.query
    assert qwp.params == ["^A", ""]


def test_condition_regex_operator_seam(sql_dialect: SQLDialect) -> None:
    """`_build_condition_regex_operator` is the seam native-regex dialects
    (MySQL REGEXP, PostgreSQL ~, SQLite REGEXP) build on via super()."""
    query: list[str] = []
    params: list[object] = []
    cond = Condition(condition=ConditionEnum.REGEX, identifier="name", value="^A", flags="i")
    sql_dialect._build_condition_regex_operator(query, params, cond, "REGEXP", "NOT REGEXP")
    assert "".join(query) == '"name" REGEXP ?'
    assert params == ["(?i)^A"]


def test_cast_equality_for_scalar_values(sql_dialect: SQLDialect) -> None:
    """cast=True with a real scalar value casts both sides to a common SQL
    type (used by empty()/notEmpty() to compare a possibly-numeric column
    against the empty string) -- this was previously unimplemented."""
    cond = Condition(condition=ConditionEnum.EQUALS, identifier="col", value="", cast=True)
    query: list[str] = []
    params: list[object] = []
    sql_dialect._build_condition_equals(query, params, cond)
    result = "".join(query)
    assert result.startswith('cast("col" AS ')
    assert " = cast(" in result
    assert params == [""]


def test_cast_equality_preserves_identifier_join_semantics(sql_dialect: SQLDialect) -> None:
    """cast=True with an identifier-shaped (list) value -- as used by
    JOIN ... ON a.x = b.y -- compares directly without casting or binding a
    parameter, since the value is itself a column reference."""
    cond = Condition(condition=ConditionEnum.EQUALS, identifier="a", value=["b", "id"], cast=True)
    query: list[str] = []
    params: list[object] = []
    sql_dialect._build_condition_equals(query, params, cond)
    assert "".join(query) == '"a" = "b"."id"'
    assert params == []


def test_escape_identifier_escapes_embedded_quote(sql_dialect: SQLDialect) -> None:
    """An identifier containing the quote char must have it doubled, not
    passed through unescaped."""
    assert sql_dialect.escape_identifier('we"ird') == '"we""ird"'


def test_escape_string_strips_null_byte(sql_dialect: SQLDialect) -> None:
    """Matches SQLDialect::ESCAPE_CHARS = ["\\0" => ''] for the base dialect."""
    assert sql_dialect.escape_string("a\0b") == "'ab'"


def test_parse_datetime_falls_back_to_isoformat(sql_dialect: SQLDialect) -> None:
    """When the value doesn't match the dialect's own DATETIME_FORMAT, PHP
    falls back to a more permissive parse (`new DateTime($string)`) before
    giving up."""
    from datetime import datetime

    result = sql_dialect.parse_datetime("2024-01-02T03:04:05")
    assert isinstance(result, datetime)
    assert result.year == 2024 and result.month == 1 and result.day == 2


def test_alter_table_raw_sql_is_rendered_verbatim(sql_dialect: SQLDialect) -> None:
    """AltersMixin.alter(sql) emits a RawAlter(sql=...) (mirrors PHP's
    Query::raw($sql) fallback) -- it must not be silently dropped."""
    from flowlab.modules.db.query.ddl import RawAlter

    qwps = sql_dialect.alter_table(table="t", alters=[RawAlter(sql="DO SOMETHING WEIRD")])
    assert len(qwps) == 1
    assert "DO SOMETHING WEIRD" in qwps[0].query


def test_alter_column_raw_sql_tail_is_rendered(sql_dialect: SQLDialect) -> None:
    """AltersMixin.alter_column(column, sql) always populates AlterColumn.sql
    with the raw ALTER COLUMN tail -- mirrors PHP's
    buildAlterTableAlterColumn(), which appends $alterColumn->sql verbatim."""
    from flowlab.modules.db.query.ddl import AlterColumn

    qwps = sql_dialect.alter_table(
        table="t",
        alters=[AlterColumn(column="age", sql="TYPE BIGINT")],
    )
    assert qwps[0].query == 'ALTER TABLE "t" ALTER COLUMN "age" TYPE BIGINT'


def test_alter_table_add_foreign_key_includes_referential_actions(sql_dialect: SQLDialect) -> None:
    """The base ANSI dialect's ADD FOREIGN KEY alter must include
    ON DELETE/ON UPDATE just like the CREATE TABLE constraint path does --
    both share the same _build_foreign_key_constraint() seam."""
    from flowlab.modules.db.query.ddl import AddForeignKeyConstraint

    qwps = sql_dialect.alter_table(
        table="t",
        alters=[
            AddForeignKeyConstraint(
                columns=["author_id"],
                ref_table="users",
                ref_columns=["id"],
                name=None,
                on_delete="CASCADE",
                on_update="RESTRICT",
            )
        ],
    )
    query = qwps[0].query
    assert "FOREIGN KEY" in query
    assert "ON DELETE CASCADE" in query
    assert "ON UPDATE RESTRICT" in query


def test_create_table_raw_constraint_is_rendered_verbatim(sql_dialect: SQLDialect) -> None:
    """ConstraintsMixin.constraint(sql) emits a RawConstraint(sql=...) --
    it must not be silently dropped from CREATE TABLE."""
    from flowlab.modules.db.query.ddl import Column, RawConstraint

    qwp = sql_dialect.create_table(
        if_not_exists=False,
        table="t",
        columns=[Column(name="id", type=TypeEnum.INT)],
        primary_keys=None,
        constraints=[RawConstraint(sql="CHECK (id > 0)")],
    )
    assert "CHECK (id > 0)" in qwp.query
