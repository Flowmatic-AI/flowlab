from __future__ import annotations

import pytest

from flowlab.modules.db import QueryError, QueryWithParams
from flowlab.modules.db.dialects import SQLDialect, SQLiteDialect
from flowlab.modules.db.query import AlterTableQuery
from flowlab.modules.db.query.enums import ReferentialActionEnum


def test_alter_table_add_column(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_column("email", "VARCHAR", not_null=True)
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], QueryWithParams)
    assert "ALTER TABLE" in result[0].query
    assert "ADD COLUMN" in result[0].query
    assert '"email"' in result[0].query


def test_alter_table_rename_column(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.rename_column("old_name", "new_name")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "RENAME COLUMN" in result[0].query
    assert '"old_name"' in result[0].query
    assert '"new_name"' in result[0].query


def test_alter_table_drop_column(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.drop_column("email")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "DROP COLUMN" in result[0].query
    assert '"email"' in result[0].query


def test_alter_table_add_primary_key(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_primary_keys("id")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "ADD PRIMARY KEY" in result[0].query
    assert '"id"' in result[0].query


def test_alter_table_add_primary_key_multiple(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_primary_keys(["user_id", "post_id"])
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "ADD PRIMARY KEY" in result[0].query
    assert '"user_id"' in result[0].query
    assert '"post_id"' in result[0].query


def test_alter_table_add_unique_constraint(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_unique_constraint(["email"])
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "UNIQUE" in result[0].query
    assert '"email"' in result[0].query


def test_alter_table_add_unique_constraint_named(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_unique_constraint(["email"], name="uq_users_email")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "UNIQUE" in result[0].query
    assert "CONSTRAINT" in result[0].query
    assert '"uq_users_email"' in result[0].query


def test_alter_table_add_foreign_key(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "posts", database=mock_db)
    q.add_foreign_key_constraint("user_id", "users", "id")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "FOREIGN KEY" in result[0].query
    assert "REFERENCES" in result[0].query
    assert '"user_id"' in result[0].query
    assert '"users"' in result[0].query
    assert '"id"' in result[0].query


def test_alter_table_add_foreign_key_named(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "posts", database=mock_db)
    q.add_foreign_key_constraint("user_id", "users", "id", name="fk_posts_user")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "FOREIGN KEY" in result[0].query
    assert "REFERENCES" in result[0].query
    assert "CONSTRAINT" in result[0].query
    assert '"fk_posts_user"' in result[0].query


def test_alter_table_drop_constraint(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "posts", database=mock_db)
    q.drop_constraint("fk_user_id")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "DROP CONSTRAINT" in result[0].query
    assert '"fk_user_id"' in result[0].query


def test_alter_table_convenience_methods(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_bool("is_active", not_null=True, default=True)
    q.add_int("age", not_null=False, default=0)
    q.add_float("score", not_null=False, default=0.0)
    q.add_string("name", size=100, not_null=True)
    q.add_text("bio")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 5

    queries = [r.query for r in result]
    combined = " ".join(queries)
    assert '"is_active"' in combined
    assert '"age"' in combined
    assert '"score"' in combined
    assert '"name"' in combined
    assert '"bio"' in combined


def test_alter_table_multiple_alters(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_column("email", "VARCHAR")
    q.add_column("age", "INTEGER")
    q.rename_column("email", "user_email")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 3

    assert "ADD COLUMN" in result[0].query
    assert "ADD COLUMN" in result[1].query
    assert "RENAME COLUMN" in result[2].query


def test_alter_table_to_sql(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_column("email", "VARCHAR")
    q.drop_column("temp_col")
    sql_list = q.to_sql()

    assert isinstance(sql_list, list)
    assert len(sql_list) == 2
    assert isinstance(sql_list[0], str)
    assert isinstance(sql_list[1], str)
    assert "ALTER TABLE" in sql_list[0]
    assert "ADD COLUMN" in sql_list[0]
    assert "DROP COLUMN" in sql_list[1]


def test_alter_table_add_column_sqlite(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    q = AlterTableQuery(sqlite_dialect, "users", database=mock_db)
    q.add_column("email", "VARCHAR(255)")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "ALTER TABLE" in result[0].query
    assert "ADD COLUMN" in result[0].query


def test_alter_table_rename_column_sqlite_ok(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    """SQLite 3.45 supports RENAME COLUMN (>= 3.25)."""
    q = AlterTableQuery(sqlite_dialect, "users", database=mock_db)
    q.rename_column("old_name", "new_name")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "RENAME COLUMN" in result[0].query


def test_alter_table_drop_column_sqlite_ok(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    """SQLite 3.45 supports DROP COLUMN (>= 3.35)."""
    q = AlterTableQuery(sqlite_dialect, "users", database=mock_db)
    q.drop_column("email")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "DROP COLUMN" in result[0].query


def test_alter_table_add_primary_key_sqlite_raises(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    q = AlterTableQuery(sqlite_dialect, "users", database=mock_db)
    q.add_primary_keys("id")

    with pytest.raises(QueryError, match="Constraint alteration.*is not supported by SQLite"):
        q.to_query_with_params()


def test_alter_table_add_unique_constraint_sqlite_raises(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    q = AlterTableQuery(sqlite_dialect, "users", database=mock_db)
    q.add_unique_constraint(["email"])

    with pytest.raises(QueryError, match="Constraint alteration.*is not supported by SQLite"):
        q.to_query_with_params()


def test_alter_table_add_foreign_key_sqlite_raises(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    q = AlterTableQuery(sqlite_dialect, "posts", database=mock_db)
    q.add_foreign_key_constraint("user_id", "users", "id")

    with pytest.raises(QueryError, match="Constraint alteration.*is not supported by SQLite"):
        q.to_query_with_params()


def test_alter_table_drop_constraint_sqlite_raises(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    q = AlterTableQuery(sqlite_dialect, "posts", database=mock_db)
    q.drop_constraint("fk_user_id")

    with pytest.raises(QueryError, match="Constraint alteration.*is not supported by SQLite"):
        q.to_query_with_params()


def test_alter_table_to_sql_sqlite(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    q = AlterTableQuery(sqlite_dialect, "users", database=mock_db)
    q.add_column("email", "VARCHAR(255)")
    sql_list = q.to_sql()

    assert isinstance(sql_list, list)
    assert len(sql_list) == 1
    assert isinstance(sql_list[0], str)
    assert "ALTER TABLE" in sql_list[0]
    assert "ADD COLUMN" in sql_list[0]


def test_alter_table_add_column_with_default(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_column("status", "VARCHAR", default="active")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "ALTER TABLE" in result[0].query
    assert "ADD COLUMN" in result[0].query
    assert '"status"' in result[0].query


def test_alter_table_add_column_not_null(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_column("email", "VARCHAR", not_null=True)
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "NOT NULL" in result[0].query


def test_alter_table_add_column_identity(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_column("id", "INTEGER", generated_by_default_as_identity=True)
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "GENERATED BY DEFAULT AS IDENTITY" in result[0].query


def test_alter_table_add_foreign_key_with_actions(sql_dialect: SQLDialect, mock_db) -> None:
    """Base ANSI dialect stores referential actions but doesn't emit them in alter queries."""
    q = AlterTableQuery(sql_dialect, "posts", database=mock_db)
    q.add_foreign_key_constraint(
        "user_id",
        "users",
        "id",
        name="fk_posts_user",
        on_delete=ReferentialActionEnum.CASCADE,
        on_update=ReferentialActionEnum.SET_NULL,
    )
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "FOREIGN KEY" in result[0].query
    assert "REFERENCES" in result[0].query
    assert "CONSTRAINT" in result[0].query
    assert '"fk_posts_user"' in result[0].query


def test_alter_table_add_identity(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_identity("id")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 2
    assert "ADD PRIMARY KEY" in result[0].query
    assert "GENERATED BY DEFAULT AS IDENTITY" in result[1].query


def test_alter_table_add_auto_increment(sql_dialect: SQLDialect, mock_db) -> None:
    q = AlterTableQuery(sql_dialect, "users", database=mock_db)
    q.add_auto_increment("id")
    result = q.to_query_with_params()

    assert isinstance(result, list)
    assert len(result) == 2
    assert "ADD PRIMARY KEY" in result[0].query
    assert "GENERATED BY DEFAULT AS IDENTITY" in result[1].query
