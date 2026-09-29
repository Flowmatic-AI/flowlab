from __future__ import annotations

from flowlab.modules.db import QueryWithParams
from flowlab.modules.db.dialects import PostgresqlDialect


def test_pg_select(pg_dialect: PostgresqlDialect) -> None:
    qwp: QueryWithParams = pg_dialect.select(
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


def test_pg_distinct_on(pg_dialect: PostgresqlDialect) -> None:
    qwp: QueryWithParams = pg_dialect.select(
        distinct=["category"],
        columns=["category", "name"],
        table="items",
        joins=None,
        where=None,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert "DISTINCT ON" in qwp.query


def test_pg_on_conflict_do_nothing(pg_dialect: PostgresqlDialect) -> None:
    from flowlab.modules.db.query import OnConflict

    qwp: QueryWithParams = pg_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John"}],
        on_conflict=OnConflict(conflict=["id"], updates=None),
        returning=None,
        last_insert_id=None,
    )
    assert "ON CONFLICT" in qwp.query
    assert "DO NOTHING" in qwp.query


def test_pg_on_conflict_do_update(pg_dialect: PostgresqlDialect) -> None:
    from flowlab.modules.db.query import OnConflict
    from flowlab.modules.db.query.expressions import Excluded

    qwp: QueryWithParams = pg_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John"}],
        on_conflict=OnConflict(conflict=["id"], updates={"name": Excluded()}),
        returning=None,
        last_insert_id=None,
    )
    assert "ON CONFLICT" in qwp.query
    assert "DO UPDATE" in qwp.query


def test_pg_on_conflict_named_constraint(pg_dialect: PostgresqlDialect) -> None:
    from flowlab.modules.db.query import OnConflict

    qwp: QueryWithParams = pg_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John"}],
        on_conflict=OnConflict(conflict="users_pkey", updates=None),
        returning=None,
        last_insert_id=None,
    )
    assert 'ON CONFLICT ON CONSTRAINT "users_pkey"' in qwp.query
    assert "DO NOTHING" in qwp.query


def test_pg_on_conflict_named_constraint_do_update(pg_dialect: PostgresqlDialect) -> None:
    from flowlab.modules.db.query import OnConflict
    from flowlab.modules.db.query.expressions import Excluded

    qwp: QueryWithParams = pg_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "John"}],
        on_conflict=OnConflict(conflict="users_pkey", updates={"name": Excluded()}),
        returning=None,
        last_insert_id=None,
    )
    assert 'ON CONFLICT ON CONSTRAINT "users_pkey"' in qwp.query
    assert 'EXCLUDED."name"' in qwp.query


def test_pg_returning(pg_dialect: PostgresqlDialect) -> None:
    qwp: QueryWithParams = pg_dialect.insert(
        table="users",
        values=[{"name": "John"}],
        on_conflict=None,
        returning=["id", "name"],
        last_insert_id=None,
    )
    assert "RETURNING" in qwp.query
    assert '"id"' in qwp.query
    assert '"name"' in qwp.query


def test_pg_bool_casting(pg_dialect: PostgresqlDialect) -> None:
    assert pg_dialect.cast_bool(True) is True
    assert pg_dialect.cast_bool(False) is False
    assert pg_dialect.parse_bool("true") is True
    assert pg_dialect.parse_bool("false") is False


def test_pg_type_mapping(pg_dialect: PostgresqlDialect) -> None:
    from flowlab.modules.db.query.enums import TypeEnum

    assert pg_dialect.type(TypeEnum.BOOL) == "BOOLEAN"
    assert pg_dialect.type(TypeEnum.INT) == "INTEGER"
    assert pg_dialect.type(TypeEnum.FLOAT) == "REAL"
    assert pg_dialect.type(TypeEnum.FLOAT, 64) == "DOUBLE PRECISION"
    assert pg_dialect.type(TypeEnum.DATETIME) == "TIMESTAMPTZ"


def test_pg_like_case_sensitive_by_default(pg_dialect: PostgresqlDialect) -> None:
    """PgSQLDialect::buildConditionLike: no version gate -- plain LIKE is the
    (case-sensitive) default; ILIKE is used only when case_insensitive was
    explicitly requested."""
    from flowlab.modules.db.query import Condition
    from flowlab.modules.db.query.enums import ConditionEnum

    cond = Condition(condition=ConditionEnum.LIKE, identifier="name", value="%john%")
    parts: list[str] = []
    params: list[object] = []
    pg_dialect._build_condition(parts, params, cond)
    result = "".join(parts)
    assert result == '"name" LIKE ?'
    assert "ILIKE" not in result


def test_pg_ilike_when_case_insensitive(pg_dialect: PostgresqlDialect) -> None:
    from flowlab.modules.db.query import Condition
    from flowlab.modules.db.query.enums import ConditionEnum

    cond = Condition(condition=ConditionEnum.LIKE, identifier="name", value="%john%", case_insensitive=True)
    parts: list[str] = []
    params: list[object] = []
    pg_dialect._build_condition(parts, params, cond)
    assert "".join(parts) == '"name" ILIKE ?'

    not_cond = Condition(condition=ConditionEnum.NOT_LIKE, identifier="name", value="%john%", case_insensitive=True)
    parts2: list[str] = []
    params2: list[object] = []
    pg_dialect._build_condition(parts2, params2, not_cond)
    assert "".join(parts2) == '"name" NOT ILIKE ?'


def test_pg_version_gating(pg_dialect: PostgresqlDialect) -> None:
    assert pg_dialect.distinct_on is True
    assert pg_dialect.lateral is True
    assert pg_dialect.on_conflict is True
    assert pg_dialect.returning is True
