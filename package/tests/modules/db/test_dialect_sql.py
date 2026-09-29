from __future__ import annotations

from flowlab.modules.db import QueryWithParams
from flowlab.modules.db.dialects import SQLDialect
from flowlab.modules.db.query.ddl import Column
from flowlab.modules.db.query.enums import TypeEnum
from flowlab.modules.db.query.expressions import Alias, Raw


def test_select_simple(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.select(
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


def test_select_star(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.select(
        distinct=None,
        columns=None,
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
    assert qwp.query == 'SELECT * FROM "users"'


def test_select_distinct(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.select(
        distinct=[],
        columns=["name"],
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
    assert "DISTINCT" in qwp.query


def test_select_with_where(sql_dialect: SQLDialect) -> None:
    from flowlab.modules.db.query import Condition
    from flowlab.modules.db.query.enums import ConditionEnum

    where: list[Condition] = [
        Condition(condition=ConditionEnum.EQUALS, identifier="id", value=1),
    ]
    qwp: QueryWithParams = sql_dialect.select(
        distinct=None,
        columns=None,
        table="users",
        joins=None,
        where=where,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    assert "WHERE" in qwp.query
    assert "?" in qwp.query
    assert 1 in qwp.params


def test_select_with_limit_offset(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.select(
        distinct=None,
        columns=None,
        table="users",
        joins=None,
        where=None,
        group_by=None,
        having=None,
        order_by=None,
        limit=10,
        offset=20,
        unions=None,
    )
    assert "LIMIT 10" in qwp.query
    assert "OFFSET 20" in qwp.query


def test_select_with_order_by(sql_dialect: SQLDialect) -> None:
    from flowlab.modules.db.query import OrderBy
    from flowlab.modules.db.query.enums import OrderByDirectionEnum

    ob: list[OrderBy] = [OrderBy(column="name", direction=OrderByDirectionEnum.ASC)]
    qwp: QueryWithParams = sql_dialect.select(
        distinct=None,
        columns=None,
        table="users",
        joins=None,
        where=None,
        group_by=None,
        having=None,
        order_by=ob,
        limit=None,
        offset=None,
        unions=None,
    )
    assert 'ORDER BY "name" ASC' in qwp.query


def test_insert_simple(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.insert(
        table="users",
        values=[{"name": "John", "age": 30}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    assert "INSERT INTO" in qwp.query
    assert '"name"' in qwp.query
    assert '"age"' in qwp.query


def test_insert_multiple_rows(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.insert(
        table="users",
        values=[{"name": "John"}, {"name": "Jane"}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    assert qwp.query.count("VALUES") == 1
    assert qwp.query.count("(") >= 3


def test_update_simple(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.update(
        table="users",
        updates={"name": "John"},
        where=None,
        returning=None,
    )
    assert "UPDATE" in qwp.query
    assert "SET" in qwp.query
    assert '"name"' in qwp.query


def test_update_with_where(sql_dialect: SQLDialect) -> None:
    from flowlab.modules.db.query import Condition
    from flowlab.modules.db.query.enums import ConditionEnum

    where: list[Condition] = [Condition(condition=ConditionEnum.EQUALS, identifier="id", value=1)]
    qwp: QueryWithParams = sql_dialect.update(
        table="users",
        updates={"name": "Jane"},
        where=where,
        returning=None,
    )
    assert "WHERE" in qwp.query


def test_delete_simple(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.delete(
        table="users",
        where=None,
        returning=None,
    )
    assert qwp.query == 'DELETE FROM "users"'


def test_delete_with_where(sql_dialect: SQLDialect) -> None:
    from flowlab.modules.db.query import Condition
    from flowlab.modules.db.query.enums import ConditionEnum

    where: list[Condition] = [Condition(condition=ConditionEnum.EQUALS, identifier="id", value=5)]
    qwp: QueryWithParams = sql_dialect.delete(
        table="users",
        where=where,
        returning=None,
    )
    assert "WHERE" in qwp.query
    assert "?" in qwp.query


def test_build_column_auto_increment_drops_default(sql_dialect: SQLDialect) -> None:
    """An auto-increment column generates its own values, so a DEFAULT next to
    one is rejected -- PostgreSQL: "both default and identity specified for
    column", MySQL: error 1067. The identity clause wins."""
    col = Column(name="id", type=TypeEnum.INT, not_null=True, auto_increment=True, default=5)
    assert sql_dialect._build_column(col) == '"id" INTEGER NOT NULL GENERATED BY DEFAULT AS IDENTITY'


def test_build_column_emits_no_keyword_without_identity_support(sql_dialect: SQLDialect) -> None:
    """AUTOINCREMENT is SQLite's spelling, not a portable fallback -- a dialect
    that doesn't do identity columns appends its own keyword in its
    _build_column() override. The base still drops the default."""
    sql_dialect.generated_by_default_as_identity = False
    col = Column(name="id", type=TypeEnum.INT, not_null=True, auto_increment=True, default=5)
    assert sql_dialect._build_column(col) == '"id" INTEGER NOT NULL'


def test_create_table(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.create_table(
        if_not_exists=False,
        table="users",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="name", type=TypeEnum.STRING, not_null=True),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    assert "CREATE TABLE" in qwp.query
    assert '"users"' in qwp.query
    assert '"id"' in qwp.query
    assert '"name"' in qwp.query
    assert "PRIMARY KEY" in qwp.query


def test_drop_table(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.drop_table(if_exists=False, table="users")
    assert qwp.query == 'DROP TABLE "users"'


def test_drop_table_if_exists(sql_dialect: SQLDialect) -> None:
    qwp: QueryWithParams = sql_dialect.drop_table(if_exists=True, table="users")
    assert qwp.query == 'DROP TABLE IF EXISTS "users"'


def test_transaction_queries(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.begin_transaction().query == "BEGIN TRANSACTION"
    assert sql_dialect.commit_transaction().query == "COMMIT TRANSACTION"
    assert sql_dialect.rollback_transaction().query == "ROLLBACK TRANSACTION"


def test_savepoint_queries(sql_dialect: SQLDialect) -> None:
    sp = sql_dialect.begin_savepoint("sp1")
    assert "SAVEPOINT" in sp.query
    assert '"sp1"' in sp.query

    rsp = sql_dialect.commit_savepoint("sp1")
    assert "RELEASE SAVEPOINT" in rsp.query

    rbsp = sql_dialect.rollback_savepoint("sp1")
    assert "ROLLBACK TO SAVEPOINT" in rbsp.query


def test_escape_identifier(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.escape_identifier("col") == '"col"'


def test_escape_identifier_list(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.escape_identifier(["schema", "table"]) == '"schema"."table"'


def test_escape_identifier_nested_list(sql_dialect: SQLDialect) -> None:
    """Escaping recurses into a list, so a qualified identifier stays qualified
    however deeply it is nested."""
    assert sql_dialect.escape_identifier([["schema", "table"], "column"]) == '"schema"."table"."column"'


def test_escape_identifier_expressions(sql_dialect: SQLDialect) -> None:
    """A raw expression is rendered as-is and an alias as `<identifier> AS
    <alias>`, both with their parts escaped by the same rules."""
    assert sql_dialect.escape_identifier(Raw("count(*)")) == "count(*)"
    assert sql_dialect.escape_identifier(Alias(["users", "email"], "mail")) == '"users"."email" AS "mail"'


def test_type_mapping(sql_dialect: SQLDialect) -> None:
    assert "INTEGER" in sql_dialect.type(TypeEnum.INT)
    assert "VARCHAR" in sql_dialect.type(TypeEnum.STRING)
    assert sql_dialect.type(TypeEnum.STRING, 50) == "VARCHAR(50)"


def test_cast_to_query(sql_dialect: SQLDialect) -> None:
    assert sql_dialect.cast_to_query(None) == "NULL"
    assert sql_dialect.cast_to_query(True) == "1"
    assert sql_dialect.cast_to_query(42) == "42"
    assert sql_dialect.cast_to_query("hello") == "'hello'"
    assert sql_dialect.cast_to_query(3.14) == "3.140000000000000124344978758017532527446746826171875"
    assert sql_dialect.cast_to_query(2.0) == "2.0"


def test_cast_to_driver(sql_dialect: SQLDialect) -> None:
    from datetime import UTC, datetime

    assert sql_dialect.cast_to_driver(None) is None
    assert sql_dialect.cast_to_driver(True) == 1
    assert sql_dialect.cast_to_driver(False) == 0
    assert sql_dialect.cast_to_driver(42) == 42
    assert sql_dialect.cast_to_driver(3.14) == 3.14
    assert sql_dialect.cast_to_driver("hello") == "hello"
    assert sql_dialect.cast_to_driver(datetime(2026, 8, 3, 12, 30, 45, tzinfo=UTC)) == "2026-08-03 12:30:45"


def test_base_on_conflict_is_a_noop_when_dialect_lacks_support(sql_dialect: SQLDialect) -> None:
    """The base ANSI dialect sets `on_conflict = False` by default (mirrors
    SQLDialect::ON_CONFLICT = false), so buildOnConflict() must return
    early and silently drop the clause -- matching PHP's
    `if (!$this->onConflict()) { return; }` gate -- regardless of what
    on_conflict value was passed in."""
    from flowlab.modules.db.query import OnConflict

    qwp: QueryWithParams = sql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "x"}],
        on_conflict=OnConflict(conflict=["id"], updates=None),
        returning=None,
        last_insert_id=None,
    )
    assert "ON CONFLICT" not in qwp.query


def test_base_on_conflict_column_list(sql_dialect: SQLDialect) -> None:
    """With on_conflict support enabled, a column-list conflict target
    renders as `ON CONFLICT (col) DO ...`."""
    from flowlab.modules.db.query import OnConflict

    sql_dialect.on_conflict = True
    qwp: QueryWithParams = sql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "x"}],
        on_conflict=OnConflict(conflict=["id"], updates=None),
        returning=None,
        last_insert_id=None,
    )
    assert 'ON CONFLICT ("id")' in qwp.query
    assert "DO NOTHING" in qwp.query


def test_base_on_conflict_named_constraint(sql_dialect: SQLDialect) -> None:
    """PHP's base SQLDialect::buildOnConflict *does* support named
    constraints, rendering `ON CONFLICT ON CONSTRAINT "name" DO ...` --
    it does not raise. (Individual dialects like SQLite override
    buildOnConflict to raise when their DB has no such syntax, but that is
    dialect-specific, not base behaviour.)"""
    from flowlab.modules.db.query import OnConflict

    sql_dialect.on_conflict = True
    qwp: QueryWithParams = sql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "x"}],
        on_conflict=OnConflict(conflict="users_pkey", updates=None),
        returning=None,
        last_insert_id=None,
    )
    assert 'ON CONFLICT ON CONSTRAINT "users_pkey"' in qwp.query
    assert "DO NOTHING" in qwp.query


def test_base_on_conflict_do_update_excluded_all_columns(sql_dialect: SQLDialect) -> None:
    """An empty (but non-None) updates dict means "update every column from
    the insert values", referencing EXCLUDED -- and the column list is the
    union across *all* rows, not just the first."""
    from flowlab.modules.db.query import OnConflict

    sql_dialect.on_conflict = True
    qwp: QueryWithParams = sql_dialect.insert(
        table="users",
        values=[{"id": 1, "name": "x"}, {"id": 2, "email": "e@x.com"}],
        on_conflict=OnConflict(conflict=["id"], updates={}),
        returning=None,
        last_insert_id=None,
    )
    assert 'DO UPDATE SET "id" = EXCLUDED."id", "name" = EXCLUDED."name", "email" = EXCLUDED."email"' in qwp.query


def test_base_returning_is_a_noop_when_dialect_lacks_support(sql_dialect: SQLDialect) -> None:
    """The base ANSI dialect sets `returning = False` by default (mirrors
    SQLDialect::RETURNING = false)."""
    qwp: QueryWithParams = sql_dialect.insert(
        table="users",
        values=[{"id": 1}],
        on_conflict=None,
        returning=["id"],
        last_insert_id=None,
    )
    assert "RETURNING" not in qwp.query


def test_base_returning_enabled(sql_dialect: SQLDialect) -> None:
    sql_dialect.returning = True
    qwp: QueryWithParams = sql_dialect.insert(
        table="users",
        values=[{"id": 1}],
        on_conflict=None,
        returning=["id", "name"],
        last_insert_id=None,
    )
    assert 'RETURNING "id", "name"' in qwp.query
