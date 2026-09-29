from __future__ import annotations

import pytest

from flowlab.modules.db import QueryError, QueryWithParams
from flowlab.modules.db.dialects import SQLiteDialect
from flowlab.modules.db.query import Condition
from flowlab.modules.db.query.enums import ConditionEnum


def test_sqlite_select(sqlite_dialect: SQLiteDialect) -> None:
    qwp: QueryWithParams = sqlite_dialect.select(
        distinct=None,
        columns=["id", "name"],
        table="users",
        joins=None,
        where=None,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert qwp.query == 'SELECT "id", "name" FROM "users"'


def test_sqlite_on_conflict(sqlite_dialect: SQLiteDialect) -> None:
    from flowlab.modules.db.query import OnConflict

    qwp: QueryWithParams = sqlite_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John"}],
        on_conflict=OnConflict(conflict=["id"], updates=None),
        returning=None,
        last_insert_id=None,
    )
    assert "ON CONFLICT" in qwp.query
    assert "DO NOTHING" in qwp.query


def test_sqlite_on_conflict_named_constraint_raises(
    sqlite_dialect: SQLiteDialect,
) -> None:
    from flowlab.modules.db.query import OnConflict

    with pytest.raises(QueryError, match="Named ON CONFLICT"):
        sqlite_dialect.insert(
            table="users",
            values=[{"id": 1, "name": "John"}],
            on_conflict=OnConflict(conflict="users_pkey", updates=None),
            returning=None,
            last_insert_id=None,
        )


def test_sqlite_returning(sqlite_dialect: SQLiteDialect) -> None:
    qwp: QueryWithParams = sqlite_dialect.insert(
        table="users",
        values=[{"name": "John"}],
        on_conflict=None,
        returning=["id"],
        last_insert_id=None,
    )
    assert "RETURNING" in qwp.query
    assert '"id"' in qwp.query


def test_sqlite_type_mapping(sqlite_dialect: SQLiteDialect) -> None:
    from flowlab.modules.db.query.enums import TypeEnum

    assert sqlite_dialect.type(TypeEnum.BOOL) == "BOOLEAN"
    assert sqlite_dialect.type(TypeEnum.INT) == "INTEGER"
    assert sqlite_dialect.type(TypeEnum.FLOAT) == "REAL"
    assert sqlite_dialect.type(TypeEnum.DATETIME) == "DATETIME"


def test_sqlite_no_distinct_on(sqlite_dialect: SQLiteDialect) -> None:
    assert not sqlite_dialect.distinct_on


def test_sqlite_no_generated_identity(sqlite_dialect: SQLiteDialect) -> None:
    assert not sqlite_dialect.generated_by_default_as_identity


def test_sqlite_auto_increment_column(sqlite_dialect: SQLiteDialect) -> None:
    from flowlab.modules.db.query.ddl import Column
    from flowlab.modules.db.query.enums import TypeEnum

    col = Column(name="id", type=TypeEnum.INT, auto_increment=True)
    col_def: str = sqlite_dialect._build_column(col)
    assert "PRIMARY KEY AUTOINCREMENT" in col_def


def test_sqlite_glob_condition(sqlite_dialect: SQLiteDialect) -> None:
    cond = Condition(condition=ConditionEnum.GLOB, identifier="name", value="foo*")
    query_parts: list[str] = []
    params: list[object] = []
    sqlite_dialect._build_condition(query_parts, params, cond)
    result = "".join(query_parts)
    assert "GLOB" in result


def test_sqlite_alter_raises(sqlite_dialect: SQLiteDialect) -> None:
    from flowlab.modules.db.query.ddl import AddPrimaryKeys, AlterColumn

    with pytest.raises(QueryError):
        sqlite_dialect._build_alter("test", AlterColumn(column="age", sql="TYPE BIGINT"))

    with pytest.raises(QueryError):
        sqlite_dialect._build_alter("test", AddPrimaryKeys(columns=["id"]))
