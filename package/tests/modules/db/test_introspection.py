"""Tests for ``list_tables()`` and ``describe_table()``.

The SQLite half runs against a real in-memory database, so it needs no
external service. The PostgreSQL and MySQL halves only assert on the SQL the
dialect renders — the live round-trips live in the integration modules.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import sys
from collections.abc import Iterator

import pytest

from flowlab.modules.db import QueryError
from flowlab.modules.db.database import DB
from flowlab.modules.db.database._introspection import (
    parse_columns,
    parse_constraints,
    parse_indexes,
    parse_primary_keys,
)
from flowlab.modules.db.dialects import MySQLDialect, PostgresqlDialect, SQLDialect, SQLiteDialect
from flowlab.modules.db.query.ddl import TableConstraints, TableDescription
from flowlab.modules.db.query.enums import ReferentialActionEnum, TypeEnum
from flowlab.modules.db.result import ResultABC


@pytest.fixture
def db() -> Iterator[DB]:
    """Yield an in-memory SQLite database holding a roles/users schema."""
    database = DB.connect_sqlite(":memory:")

    database.create_table("roles").identity("id").string("code", 10, not_null=True).execute()
    database.create_table("users").identity("id").string("name", 64, not_null=True, default="anon").string(
        "email", 120
    ).integer("role_id").unique_constraint(["email"]).unique_constraint(["name", "email"]).foreign_key_constraint(
        "role_id",
        "roles",
        "id",
        on_delete=ReferentialActionEnum.CASCADE,
        on_update=ReferentialActionEnum.SET_NULL,
    ).execute()

    try:
        yield database
    finally:
        database.close()


def test_describe_table_returns_a_table_description(db: DB) -> None:
    description = db.describe_table("users")

    assert isinstance(description, TableDescription)
    assert isinstance(description.constraints, TableConstraints)


def test_describe_table_columns(db: DB) -> None:
    columns = db.describe_table("users").columns

    assert [column.name for column in columns] == ["id", "name", "email", "role_id"]
    assert columns[1].type == TypeEnum.STRING
    assert columns[1].size == 64
    assert columns[1].not_null is True
    # The value the column was declared with, not the literal that spelled it.
    assert columns[1].default == "anon"
    assert columns[2].not_null is False


def test_describe_table_recovers_every_type_enum(db: DB) -> None:
    """A column declared through the builders describes back as it was declared.

    SQLite has a single float type and stores no datetime precision, so those
    two widths cannot survive the round-trip.
    """
    db.create_table("spread_types").identity("id").boolean("flag").integer("n32", 32).integer("n64", 64).float(
        "f32", 32
    ).float("f64", 64).string("s64", 64).string("s255").text("body").datetime("seen_at").json("payload").execute()

    columns = db.describe_table("spread_types").columns

    assert [(column.name, column.type, column.size) for column in columns] == [
        ("id", TypeEnum.INT, 64),
        ("flag", TypeEnum.BOOL, None),
        ("n32", TypeEnum.INT, 32),
        ("n64", TypeEnum.INT, 64),
        ("f32", TypeEnum.FLOAT, 64),
        ("f64", TypeEnum.FLOAT, 64),
        ("s64", TypeEnum.STRING, 64),
        ("s255", TypeEnum.STRING, 255),
        ("body", TypeEnum.STRING, sys.maxsize),
        ("seen_at", TypeEnum.DATETIME, None),
        ("payload", TypeEnum.JSON, None),
    ]


def test_describe_table_reports_auto_increment(db: DB) -> None:
    columns = db.describe_table("users").columns

    assert columns[0].auto_increment is True
    # The sequence backing the column is not a default the table declared.
    assert columns[0].default is None
    assert columns[1].auto_increment is False


def test_describe_table_unique_constraints(db: DB) -> None:
    unique = db.describe_table("users").constraints.unique

    assert [constraint.columns for constraint in unique] == [["email"], ["name", "email"]]


def test_describe_table_foreign_keys(db: DB) -> None:
    foreign_keys = db.describe_table("users").constraints.foreign_keys

    assert len(foreign_keys) == 1
    assert foreign_keys[0].columns == ["role_id"]
    assert foreign_keys[0].ref_table == "roles"
    assert foreign_keys[0].ref_columns == ["id"]
    # The enum the key was built with is the enum that comes back, not the
    # string the engine reported. `is` rather than `==`: a StrEnum compares
    # equal to its own value, so `==` would pass on a raw string too.
    assert foreign_keys[0].on_delete is ReferentialActionEnum.CASCADE
    assert foreign_keys[0].on_update is ReferentialActionEnum.SET_NULL


def test_describe_table_ignores_standalone_indexes(db: DB) -> None:
    db.create_index("users", "idx_users_name").columns("name").unique().execute()

    unique = db.describe_table("users").constraints.unique

    assert [constraint.columns for constraint in unique] == [["email"], ["name", "email"]]


def test_describe_table_without_constraints(db: DB) -> None:
    description = db.describe_table("roles")

    assert [column.name for column in description.columns] == ["id", "code"]
    assert description.constraints.unique == []
    assert description.constraints.foreign_keys == []


def test_describe_table_unknown_table_is_empty(db: DB) -> None:
    description = db.describe_table("nope")

    assert description.columns == []
    assert description.constraints.unique == []


def test_table_facade_describe(db: DB) -> None:
    assert db.table("users").describe().columns == db.describe_table("users").columns


def test_create_and_drop_index_round_trip(db: DB) -> None:
    db.create_index("users", "idx_users_email").columns("email").if_not_exists().execute()
    db.create_index("users", "idx_users_email").columns("email").if_not_exists().execute()

    db.drop_index("users", "idx_users_email").if_exists().execute()
    db.drop_index("users", "idx_users_email").if_exists().execute()


def test_create_and_drop_index_in_an_attached_schema(db: DB, tmp_path) -> None:
    db.exec(f"ATTACH DATABASE '{tmp_path / 'reporting.sqlite'}' AS reporting")
    db.create_table(["reporting", "metrics"]).identity("id").string("kind", 32, not_null=True).execute()

    db.create_index(["reporting", "metrics"], "idx_metrics_kind").columns("kind").if_not_exists().execute()
    db.create_index(["reporting", "metrics"], "idx_metrics_kind").columns("kind").if_not_exists().execute()

    indexes = db.query("SELECT name FROM reporting.sqlite_master WHERE type = 'index'").scalars()
    assert "idx_metrics_kind" in indexes

    db.drop_index(["reporting", "metrics"], "idx_metrics_kind").if_exists().execute()
    db.drop_index(["reporting", "metrics"], "idx_metrics_kind").if_exists().execute()

    indexes = db.query("SELECT name FROM reporting.sqlite_master WHERE type = 'index'").scalars()
    assert "idx_metrics_kind" not in indexes


def test_describe_table_in_an_attached_schema(db: DB, tmp_path) -> None:
    db.exec(f"ATTACH DATABASE '{tmp_path / 'reporting.sqlite'}' AS reporting")
    db.create_table(["reporting", "metrics"]).identity("id").string("kind", 32, not_null=True).execute()

    description = db.describe_table(["reporting", "metrics"])

    assert [column.name for column in description.columns] == ["id", "kind"]
    assert description.columns[0].auto_increment is True

    # An unqualified name still resolves, because SQLite searches main, then
    # temp, then every attached database. Only the AUTOINCREMENT probe is
    # narrower -- it reads main's sqlite_master and so misses the keyword.
    unqualified = db.describe_table("metrics")
    assert [column.name for column in unqualified.columns] == ["id", "kind"]
    assert unqualified.columns[0].auto_increment is False


def test_table_facade_create_and_drop_index(db: DB) -> None:
    db.table("users").create_index("idx_users_role_id", "role_id").execute()
    db.table("users").drop_index("idx_users_role_id").execute()


def test_list_tables(db: DB) -> None:
    assert db.list_tables() == ["roles", "users"]


def test_list_tables_ignores_the_schema_on_sqlite(db: DB) -> None:
    assert db.list_tables("reporting") == db.list_tables()


def test_list_tables_hides_sqlite_internals(db: DB) -> None:
    # The identity column gives SQLite a reason to keep sqlite_sequence around.
    db.insert("roles").values({"code": "admin"}).execute()

    assert "sqlite_sequence" in db.query("SELECT name FROM sqlite_master").scalars()
    assert db.list_tables() == ["roles", "users"]


def test_list_tables_skips_indexes_and_views(db: DB) -> None:
    db.create_index("users", "idx_users_email").columns("email").execute()
    db.exec('CREATE VIEW "active_users" AS SELECT * FROM "users"')

    assert db.list_tables() == ["roles", "users"]


def test_describe_table_rejects_an_over_qualified_name(sqlite_dialect: SQLiteDialect) -> None:
    with pytest.raises(QueryError):
        sqlite_dialect.describe_table_columns(["cluster", "app", "users"])


def test_pg_list_tables_defaults_to_public(pg_dialect: PostgresqlDialect) -> None:
    qwp = pg_dialect.list_tables("public")

    assert qwp.params == ["public"]
    assert "pg_class" in qwp.query


def test_pg_describe_table_resolves_through_to_regclass(pg_dialect: PostgresqlDialect) -> None:
    assert pg_dialect.describe_table_columns(["app", "users"]).params == ['"app"."users"']
    assert pg_dialect.describe_table_constraints("users").params == ['"users"']


def test_pg_describe_table_columns_skips_attidentity_before_10(pg_dialect: PostgresqlDialect) -> None:
    assert "attidentity" in pg_dialect.describe_table_columns("users").query
    assert "attidentity" not in PostgresqlDialect(version="9.6").describe_table_columns("users").query


def test_mysql_list_tables_ignores_the_schema(mysql_dialect: MySQLDialect) -> None:
    qwp = mysql_dialect.list_tables("public")

    assert qwp.params == []
    assert "DATABASE()" in qwp.query


def test_sqlite_list_tables_ignores_the_schema(sqlite_dialect: SQLiteDialect) -> None:
    qwp = sqlite_dialect.list_tables("public")

    assert qwp.params == []
    assert "sqlite_master" in qwp.query


def test_ansi_list_tables_honours_the_schema(sql_dialect: SQLDialect) -> None:
    qwp = sql_dialect.list_tables("public")

    assert qwp.params == ["public"]
    assert "information_schema.tables" in qwp.query


def test_mysql_describe_table_defaults_to_the_current_database(mysql_dialect: MySQLDialect) -> None:
    columns = mysql_dialect.describe_table_columns("users")
    constraints = mysql_dialect.describe_table_constraints("users")

    assert columns.params == ["users"]
    assert "c.TABLE_SCHEMA = DATABASE()" in columns.query
    assert constraints.params == ["users"]
    assert "tc.table_schema = DATABASE()" in constraints.query


def test_mysql_describe_table_takes_an_explicit_schema(mysql_dialect: MySQLDialect) -> None:
    qwp = mysql_dialect.describe_table_columns(["app", "users"])

    assert qwp.params == ["users", "app"]
    assert "c.TABLE_SCHEMA = ?" in qwp.query


def test_ansi_describe_table_uses_information_schema(sql_dialect: SQLDialect) -> None:
    assert "information_schema.columns" in sql_dialect.describe_table_columns("users").query
    assert "information_schema.table_constraints" in sql_dialect.describe_table_constraints("users").query


def test_parse_columns(sql_dialect: SQLDialect) -> None:
    columns = parse_columns(
        sql_dialect,
        [
            {
                "column_name": "id",
                "column_type": "bigint",
                "not_null": 1,
                "default_expression": "nextval('users_id_seq')",
                "auto_increment": 1,
            },
            {
                "column_name": "name",
                "column_type": "varchar(64)",
                "not_null": 0,
                "default_expression": None,
                "auto_increment": 0,
            },
        ],
    )

    assert columns[0].auto_increment is True
    assert columns[0].default is None
    assert columns[0].not_null is True
    assert columns[1].type == TypeEnum.STRING
    assert columns[1].size == 64
    assert columns[1].default is None
    assert columns[1].not_null is False


def test_parse_constraints_groups_columns_by_id() -> None:
    constraints = parse_constraints(
        [
            {
                "constraint_id": "1",
                "constraint_name": "users_pair_key",
                "constraint_type": "UNIQUE",
                "column_name": "name",
                "column_position": 1,
                "ref_table": None,
                "ref_column": None,
                "on_delete": None,
                "on_update": None,
            },
            {
                "constraint_id": "1",
                "constraint_name": "users_pair_key",
                "constraint_type": "UNIQUE",
                "column_name": "email",
                "column_position": 2,
                "ref_table": None,
                "ref_column": None,
                "on_delete": None,
                "on_update": None,
            },
            {
                "constraint_id": "2",
                "constraint_name": None,
                "constraint_type": "FOREIGN KEY",
                "column_name": "role_id",
                "column_position": 1,
                "ref_table": "roles",
                "ref_column": "id",
                "on_delete": "CASCADE",
                "on_update": "NO ACTION",
            },
        ]
    )

    assert len(constraints.unique) == 1
    assert constraints.unique[0].columns == ["name", "email"]
    assert constraints.unique[0].name == "users_pair_key"

    assert len(constraints.foreign_keys) == 1
    assert constraints.foreign_keys[0].name is None
    assert constraints.foreign_keys[0].columns == ["role_id"]
    assert constraints.foreign_keys[0].ref_columns == ["id"]
    assert constraints.foreign_keys[0].on_delete is ReferentialActionEnum.CASCADE
    assert constraints.foreign_keys[0].on_update is ReferentialActionEnum.NO_ACTION


def test_parse_constraints_keeps_an_unlisted_referential_action_as_a_string() -> None:
    """An action the enum does not list is reported raw rather than dropped.

    SET DEFAULT is the realistic case: this library will not build one because
    InnoDB does not carry it out, but a table created elsewhere may declare it
    and describing that table must not lose the rule.
    """
    constraints = parse_constraints(
        [
            {
                "constraint_id": "1",
                "constraint_name": "users_role_fk",
                "constraint_type": "FOREIGN KEY",
                "column_name": "role_id",
                "column_position": 1,
                "ref_table": "roles",
                "ref_column": "id",
                "on_delete": "SET DEFAULT",
                "on_update": None,
            },
        ]
    )

    assert constraints.foreign_keys[0].on_delete == "SET DEFAULT"
    assert not isinstance(constraints.foreign_keys[0].on_delete, ReferentialActionEnum)
    assert constraints.foreign_keys[0].on_update is None


def test_parse_constraints_ignores_other_constraint_types() -> None:
    constraints = parse_constraints(
        [
            {
                "constraint_id": "1",
                "constraint_name": "users_pkey",
                "constraint_type": "PRIMARY KEY",
                "column_name": "id",
                "column_position": 1,
                "ref_table": None,
                "ref_column": None,
                "on_delete": None,
                "on_update": None,
            },
        ]
    )

    assert constraints.unique == []
    assert constraints.foreign_keys == []


def test_describe_table_reports_the_table_it_described(db: DB) -> None:
    assert db.describe_table("users").table == "users"
    assert db.describe_table(["main", "users"]).table == ["main", "users"]


def test_describe_table_primary_keys(db: DB) -> None:
    """An identity column is a primary key, and describing says so."""
    assert db.describe_table("users").primary_keys == ["id"]


def test_describe_table_primary_key_that_is_not_an_identity(db: DB) -> None:
    db.create_table("countries").string("code", 2, not_null=True).string("name").primary_keys("code").execute()

    assert db.describe_table("countries").primary_keys == ["code"]


def test_describe_table_composite_primary_key_keeps_the_key_order(db: DB) -> None:
    db.create_table("memberships").integer("user_id").integer("role_id").primary_keys(["user_id", "role_id"]).execute()

    assert db.describe_table("memberships").primary_keys == ["user_id", "role_id"]


def test_describe_table_without_a_primary_key(db: DB) -> None:
    db.create_table("events").string("kind").execute()

    assert db.describe_table("events").primary_keys == []


def test_create_table_from_a_description_round_trips(db: DB, tmp_path) -> None:
    """A description recreates the table it came from, column for column."""
    db.exec(f"ATTACH DATABASE '{tmp_path / 'copy.sqlite'}' AS copy")

    for table in ["roles", "users"]:
        description = db.describe_table(table)
        description.table = ["copy", table]
        description.create_table(db)

    for table in ["roles", "users"]:
        original = db.describe_table(table)
        copy = db.describe_table(["copy", table])

        assert [
            (column.name, column.type, column.size, column.not_null, column.auto_increment) for column in copy.columns
        ] == [
            (column.name, column.type, column.size, column.not_null, column.auto_increment)
            for column in original.columns
        ]
        assert copy.primary_keys == original.primary_keys
        assert copy.constraints == original.constraints


def test_create_table_from_a_description_returns_a_result(db: DB) -> None:
    description = db.describe_table("roles")
    description.table = "roles_copy"

    assert isinstance(description.create_table(db), ResultABC)


def test_create_table_from_a_description_honours_if_not_exists(db: DB) -> None:
    description = db.describe_table("roles")

    with pytest.raises(sqlite3.OperationalError):
        description.create_table(db)

    description.create_table(db, if_not_exists=True)


def test_create_table_from_a_description_keeps_a_composite_primary_key(db: DB) -> None:
    db.create_table("memberships").integer("user_id").integer("role_id").primary_keys(["user_id", "role_id"]).execute()

    description = db.describe_table("memberships")
    description.table = "memberships_copy"
    description.create_table(db)

    assert db.describe_table("memberships_copy").primary_keys == ["user_id", "role_id"]


def test_create_table_from_a_description_can_skip_the_unique_constraints(db: DB) -> None:
    description = db.describe_table("users")
    description.table = "users_copy"
    description.create_table(db, skip_unique_constraints=True)

    copy = db.describe_table("users_copy")

    assert copy.constraints.unique == []
    assert [key.columns for key in copy.constraints.foreign_keys] == [["role_id"]]
    assert copy.primary_keys == ["id"]
    # Skipping is a build-time choice, not an edit of the description.
    assert [constraint.columns for constraint in description.constraints.unique] == [["email"], ["name", "email"]]


def test_create_table_from_a_description_can_skip_the_foreign_keys(db: DB) -> None:
    description = db.describe_table("users")
    description.table = "users_copy"
    description.create_table(db, skip_foreign_key_constraints=True)

    copy = db.describe_table("users_copy")

    assert copy.constraints.foreign_keys == []
    assert [constraint.columns for constraint in copy.constraints.unique] == [["email"], ["name", "email"]]
    assert [key.columns for key in description.constraints.foreign_keys] == [["role_id"]]


def test_create_table_from_a_description_can_skip_both(db: DB) -> None:
    """Columns and the primary key are not constraints the flags reach."""
    description = db.describe_table("users")
    description.table = "users_copy"
    description.create_table(db, skip_unique_constraints=True, skip_foreign_key_constraints=True)

    copy = db.describe_table("users_copy")

    assert copy.constraints.unique == []
    assert copy.constraints.foreign_keys == []
    assert copy.primary_keys == ["id"]
    assert [column.name for column in copy.columns] == [column.name for column in description.columns]


def test_create_table_from_a_description_leaves_the_description_alone(db: DB) -> None:
    """Building the statement must not hand the query the description's own lists."""
    description = db.describe_table("users")
    description.table = "users_copy"
    description.create_table(db)

    assert description.primary_keys == ["id"]
    assert [constraint.columns for constraint in description.constraints.unique] == [["email"], ["name", "email"]]


def test_parse_primary_keys_keeps_the_column_order() -> None:
    primary_keys = parse_primary_keys(
        [
            {
                "constraint_id": "1",
                "constraint_name": "memberships_pkey",
                "constraint_type": "PRIMARY KEY",
                "column_name": "user_id",
                "column_position": 1,
                "ref_table": None,
                "ref_column": None,
                "on_delete": None,
                "on_update": None,
            },
            {
                "constraint_id": "1",
                "constraint_name": "memberships_pkey",
                "constraint_type": "PRIMARY KEY",
                "column_name": "role_id",
                "column_position": 2,
                "ref_table": None,
                "ref_column": None,
                "on_delete": None,
                "on_update": None,
            },
            {
                "constraint_id": "2",
                "constraint_name": "memberships_role_unique",
                "constraint_type": "UNIQUE",
                "column_name": "role_id",
                "column_position": 1,
                "ref_table": None,
                "ref_column": None,
                "on_delete": None,
                "on_update": None,
            },
        ]
    )

    assert primary_keys == ["user_id", "role_id"]


def test_dialects_ask_for_primary_key_constraints(
    sql_dialect: SQLDialect,
    pg_dialect: PostgresqlDialect,
    mysql_dialect: MySQLDialect,
    sqlite_dialect: SQLiteDialect,
) -> None:
    assert "'PRIMARY KEY'" in sql_dialect.describe_table_constraints("users").query
    assert "'PRIMARY KEY'" in mysql_dialect.describe_table_constraints("users").query
    assert "'PRIMARY KEY'" in pg_dialect.describe_table_constraints("users").query
    assert "'PRIMARY KEY'" in sqlite_dialect.describe_table_constraints("users").query


def test_sqlite_describe_table_constraints_binds_every_pragma(sqlite_dialect: SQLiteDialect) -> None:
    """One name per pragma without a schema; name and schema per pragma with one."""
    assert sqlite_dialect.describe_table_constraints("users").params == ["users", "users", "users"]
    assert sqlite_dialect.describe_table_constraints(["app", "users"]).params == [
        "users",
        "app",
        "users",
        "app",
        "app",
        "users",
        "app",
    ]


def test_describe_table_indexes(db: DB) -> None:
    db.create_index("users", "idx_users_name").columns("name").execute()
    db.create_index("users", "idx_users_pair").columns(["name", "email"]).unique().execute()

    indexes = db.describe_table("users").indexes

    assert [(index.name, index.columns, index.unique) for index in indexes] == [
        ("idx_users_name", ["name"], False),
        ("idx_users_pair", ["name", "email"], True),
    ]


def test_describe_table_indexes_ignores_the_constraint_indexes(db: DB) -> None:
    """A unique constraint and a primary key are indexes underneath.

    They are described as constraints, so describing them as indexes too would
    make a replay build each of them twice.
    """
    assert db.describe_table("users").indexes == []
    assert [constraint.columns for constraint in db.describe_table("users").constraints.unique] == [
        ["email"],
        ["name", "email"],
    ]


def test_describe_table_skips_an_expression_or_partial_index(db: DB) -> None:
    """Neither can be rebuilt by `create_index()`, so neither is described."""
    db.exec("CREATE INDEX idx_users_lower ON users (LOWER(name))")
    db.exec("CREATE INDEX idx_users_named ON users (name) WHERE email IS NOT NULL")
    db.create_index("users", "idx_users_email").columns("email").execute()

    assert [index.name for index in db.describe_table("users").indexes] == ["idx_users_email"]


def test_describe_table_without_indexes(db: DB) -> None:
    assert db.describe_table("roles").indexes == []
    assert db.describe_table("nope").indexes == []


def test_describe_table_indexes_in_an_attached_schema(db: DB, tmp_path) -> None:
    db.exec(f"ATTACH DATABASE '{tmp_path / 'reporting.sqlite'}' AS reporting")
    db.create_table(["reporting", "metrics"]).identity("id").string("kind", 32).execute()
    db.create_index(["reporting", "metrics"], "idx_metrics_kind").columns("kind").execute()

    indexes = db.describe_table(["reporting", "metrics"]).indexes

    assert [(index.name, index.columns) for index in indexes] == [("idx_metrics_kind", ["kind"])]


def test_create_table_from_a_description_replays_the_indexes(db: DB) -> None:
    db.create_index("users", "idx_users_name").columns("name").execute()
    db.create_index("users", "idx_users_pair").columns(["name", "email"]).unique().execute()

    description = db.describe_table("users")
    description.table = "users_copy"
    # An index name is database-wide, so a copy landing beside the original needs
    # names of its own — the same rule the constraint names follow.
    description.indexes = [dataclasses.replace(index, name=f"copy_{index.name}") for index in description.indexes]
    description.create_table(db)

    copy = db.describe_table("users_copy")

    assert [(index.name, index.columns, index.unique) for index in copy.indexes] == [
        ("copy_idx_users_name", ["name"], False),
        ("copy_idx_users_pair", ["name", "email"], True),
    ]


def test_create_table_from_a_description_replays_an_index_name_verbatim(db: DB) -> None:
    """The names are replayed as described, so a same-database copy collides."""
    db.create_index("users", "idx_users_name").columns("name").execute()

    description = db.describe_table("users")

    with pytest.raises(sqlite3.OperationalError):
        description.create_table(db, override_name="users_copy")


def test_create_table_from_a_description_can_skip_the_indexes(db: DB) -> None:
    db.create_index("users", "idx_users_name").columns("name").execute()

    description = db.describe_table("users")
    description.create_table(db, override_name="users_copy", skip_indexes=True)

    assert db.describe_table("users_copy").indexes == []
    # Skipping is a build-time choice, not an edit of the description.
    assert [index.name for index in description.indexes] == ["idx_users_name"]


def test_create_table_from_a_description_guards_the_indexes_too(db: DB) -> None:
    """`if_not_exists` reaches the CREATE INDEX statements, not just the table."""
    db.create_index("users", "idx_users_name").columns("name").execute()

    description = db.describe_table("users")
    description.create_table(db, if_not_exists=True)

    assert [index.name for index in db.describe_table("users").indexes] == ["idx_users_name"]


def test_create_table_from_a_description_leaves_the_indexes_alone(db: DB) -> None:
    db.create_index("users", "idx_users_pair").columns(["name", "email"]).unique().execute()

    description = db.describe_table("users")
    description.indexes = [dataclasses.replace(index, name="copy_pair") for index in description.indexes]
    description.create_table(db, override_name="users_copy")

    assert description.indexes[0].columns == ["name", "email"]


def test_parse_indexes_groups_by_index_and_drops_what_cannot_be_replayed(
    sqlite_dialect: SQLiteDialect,
) -> None:
    indexes = parse_indexes(
        sqlite_dialect,
        [
            {
                "index_id": "1",
                "index_name": "idx_pair",
                "column_name": "name",
                "column_position": 1,
                "is_unique": 1,
                "is_partial": 0,
            },
            {
                "index_id": "1",
                "index_name": "idx_pair",
                "column_name": "email",
                "column_position": 2,
                "is_unique": 1,
                "is_partial": 0,
            },
            {
                "index_id": "2",
                "index_name": "idx_expression",
                "column_name": None,
                "column_position": 1,
                "is_unique": 0,
                "is_partial": 0,
            },
            {
                "index_id": "3",
                "index_name": "idx_partial",
                "column_name": "age",
                "column_position": 1,
                "is_unique": 0,
                "is_partial": 1,
            },
            {
                "index_id": "4",
                "index_name": "idx_age",
                "column_name": "age",
                "column_position": 1,
                "is_unique": 0,
                "is_partial": 0,
            },
        ],
    )

    assert [(index.name, index.columns, index.unique) for index in indexes] == [
        ("idx_pair", ["name", "email"], True),
        ("idx_age", ["age"], False),
    ]


def test_parse_indexes_drops_an_index_whose_first_column_already_landed(
    sqlite_dialect: SQLiteDialect,
) -> None:
    """A key the parser cannot replay disqualifies the whole index, not one column."""
    indexes = parse_indexes(
        sqlite_dialect,
        [
            {
                "index_id": "1",
                "index_name": "idx_mixed",
                "column_name": "name",
                "column_position": 1,
                "is_unique": 0,
                "is_partial": 0,
            },
            {
                "index_id": "1",
                "index_name": "idx_mixed",
                "column_name": None,
                "column_position": 2,
                "is_unique": 0,
                "is_partial": 0,
            },
            {
                "index_id": "1",
                "index_name": "idx_mixed",
                "column_name": "email",
                "column_position": 3,
                "is_unique": 0,
                "is_partial": 0,
            },
        ],
    )

    assert indexes == []


def test_dialects_alias_the_index_columns_the_same_way(
    sql_dialect: SQLDialect,
    pg_dialect: PostgresqlDialect,
    mysql_dialect: MySQLDialect,
    sqlite_dialect: SQLiteDialect,
) -> None:
    """One parser reads all four, so every dialect has to answer in the same names."""
    for dialect in [sql_dialect, pg_dialect, mysql_dialect, sqlite_dialect]:
        query = dialect.describe_table_indexes("users").query

        for alias in ["index_id", "index_name", "column_name", "column_position", "is_unique", "is_partial"]:
            assert f"AS {alias}" in query


def test_sqlite_describe_table_indexes_reads_only_the_created_indexes(
    sqlite_dialect: SQLiteDialect,
) -> None:
    query = sqlite_dialect.describe_table_indexes("users").query

    # 'c' is what pragma_index_list reports for an index CREATE INDEX made; 'u'
    # and 'pk' are the constraint ones the constraints query already reports.
    assert "il.origin = 'c'" in query


def test_sqlite_describe_table_indexes_binds_every_pragma(sqlite_dialect: SQLiteDialect) -> None:
    assert sqlite_dialect.describe_table_indexes("users").params == ["users"]
    assert sqlite_dialect.describe_table_indexes(["app", "users"]).params == ["users", "app", "app"]


def test_pg_describe_table_indexes_resolves_through_to_regclass(pg_dialect: PostgresqlDialect) -> None:
    assert pg_dialect.describe_table_indexes(["app", "users"]).params == ['"app"."users"']
    assert "to_regclass(?)" in pg_dialect.describe_table_indexes("users").query


def test_pg_describe_table_indexes_skips_include_columns_from_11(pg_dialect: PostgresqlDialect) -> None:
    assert "indnkeyatts" in pg_dialect.describe_table_indexes("users").query
    assert "indnkeyatts" not in PostgresqlDialect(version="10").describe_table_indexes("users").query


def test_pg_describe_table_indexes_leaves_the_constraint_indexes_out(
    pg_dialect: PostgresqlDialect,
) -> None:
    query = pg_dialect.describe_table_indexes("users").query

    assert "NOT i.indisprimary" in query
    assert "con.conindid = i.indexrelid" in query
    # A GIN or GiST index cannot be rebuilt by create_index() either.
    assert "am.amname = 'btree'" in query


def test_mysql_describe_table_indexes_defaults_to_the_current_database(
    mysql_dialect: MySQLDialect,
) -> None:
    qwp = mysql_dialect.describe_table_indexes("users")

    assert "DATABASE()" in qwp.query
    assert qwp.params == ["users"]
    assert mysql_dialect.describe_table_indexes(["app", "users"]).params == ["users", "app"]


def test_ansi_describe_table_indexes_uses_information_schema(sql_dialect: SQLDialect) -> None:
    query = sql_dialect.describe_table_indexes("users").query

    assert "information_schema.statistics" in query
    # The index behind a constraint is described as that constraint, not twice.
    assert "information_schema.table_constraints" in query
