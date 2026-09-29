from __future__ import annotations

import pytest

from flowlab.modules.db import QueryError, QueryWithParams
from flowlab.modules.db.dialects import MySQLDialect, PostgresqlDialect, SQLDialect, SQLiteDialect
from flowlab.modules.db.query import CreateIndexQuery, DropIndexQuery


def test_create_index(sql_dialect: SQLDialect, mock_db) -> None:
    q = CreateIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_posts_user_id")
    q.columns("user_id")
    result = q.to_query_with_params()

    assert isinstance(result, QueryWithParams)
    assert result.query == 'CREATE INDEX "idx_posts_user_id" ON "posts" ("user_id")'
    assert result.params == []


def test_create_index_multiple_columns(sql_dialect: SQLDialect, mock_db) -> None:
    q = CreateIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_posts_pair")
    q.columns(["user_id", "created_at"])
    result = q.to_query_with_params()

    assert result.query == 'CREATE INDEX "idx_posts_pair" ON "posts" ("user_id", "created_at")'


def test_create_index_column_appends(sql_dialect: SQLDialect, mock_db) -> None:
    q = CreateIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_posts_pair")
    q.column("user_id").column("created_at")
    result = q.to_query_with_params()

    assert result.query == 'CREATE INDEX "idx_posts_pair" ON "posts" ("user_id", "created_at")'


def test_create_index_unique(sql_dialect: SQLDialect, mock_db) -> None:
    q = CreateIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_posts_slug")
    q.columns("slug").unique()
    result = q.to_query_with_params()

    assert result.query == 'CREATE UNIQUE INDEX "idx_posts_slug" ON "posts" ("slug")'


def test_create_index_if_not_exists(sql_dialect: SQLDialect, mock_db) -> None:
    q = CreateIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_posts_user_id")
    q.columns("user_id").if_not_exists()
    result = q.to_query_with_params()

    assert result.query == 'CREATE INDEX IF NOT EXISTS "idx_posts_user_id" ON "posts" ("user_id")'


def test_create_index_takes_the_schema_from_the_table(sql_dialect: SQLDialect, mock_db) -> None:
    q = CreateIndexQuery(sql_dialect, ["app", "posts"], database=mock_db, name="idx_posts_user_id")
    q.columns("user_id")
    result = q.to_query_with_params()

    # ANSI, PostgreSQL and MySQL reject a qualified index name: the index is
    # created in its table's schema.
    assert result.query == 'CREATE INDEX "idx_posts_user_id" ON "app"."posts" ("user_id")'


def test_drop_index_takes_the_schema_from_the_table(sql_dialect: SQLDialect, mock_db) -> None:
    q = DropIndexQuery(sql_dialect, ["app", "posts"], database=mock_db, name="idx_posts_user_id")

    assert q.to_query_with_params().query == 'DROP INDEX "app"."idx_posts_user_id"'


def test_sqlite_create_index_qualifies_the_index_not_the_table(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    q = CreateIndexQuery(sqlite_dialect, ["app", "posts"], database=mock_db, name="idx_posts_user_id")
    q.columns("user_id")

    # SQLite is the mirror image: the schema rides on the index name and the
    # table must be bare.
    assert q.to_query_with_params().query == 'CREATE INDEX "app"."idx_posts_user_id" ON "posts" ("user_id")'


def test_sqlite_drop_index_qualifies_the_index(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    q = DropIndexQuery(sqlite_dialect, ["app", "posts"], database=mock_db, name="idx_posts_user_id")

    assert q.to_query_with_params().query == 'DROP INDEX "app"."idx_posts_user_id"'


def test_pg_create_index_leaves_the_schema_on_the_table(pg_dialect: PostgresqlDialect, mock_db) -> None:
    q = CreateIndexQuery(pg_dialect, ["app", "posts"], database=mock_db, name="idx_posts_user_id")
    q.columns("user_id")

    assert q.to_query_with_params().query == 'CREATE INDEX "idx_posts_user_id" ON "app"."posts" ("user_id")'


def test_mysql_index_name_is_never_qualified(mysql_dialect: MySQLDialect, mock_db) -> None:
    create = CreateIndexQuery(mysql_dialect, ["app", "posts"], database=mock_db, name="idx_posts_user_id")
    create.columns("user_id")
    assert create.to_query_with_params().query == ("CREATE INDEX `idx_posts_user_id` ON `app`.`posts` (`user_id`)")

    drop = DropIndexQuery(mysql_dialect, ["app", "posts"], database=mock_db, name="idx_posts_user_id")
    assert drop.to_query_with_params().query == "DROP INDEX `idx_posts_user_id` ON `app`.`posts`"


def test_create_index_without_columns_raises(sql_dialect: SQLDialect, mock_db) -> None:
    q = CreateIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_posts_user_id")

    with pytest.raises(QueryError):
        q.to_query_with_params()


def test_create_index_fluent_name_and_table(sql_dialect: SQLDialect, mock_db) -> None:
    q = CreateIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_old")
    q.name("idx_new").table("comments").columns("user_id")
    result = q.to_query_with_params()

    assert result.query == 'CREATE INDEX "idx_new" ON "comments" ("user_id")'


def test_drop_index(sql_dialect: SQLDialect, mock_db) -> None:
    q = DropIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_posts_user_id")
    result = q.to_query_with_params()

    assert result.query == 'DROP INDEX "idx_posts_user_id"'
    assert result.params == []


def test_drop_index_if_exists(sql_dialect: SQLDialect, mock_db) -> None:
    q = DropIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_posts_user_id")
    q.if_exists()
    result = q.to_query_with_params()

    assert result.query == 'DROP INDEX IF EXISTS "idx_posts_user_id"'


def test_drop_index_fluent_name_and_table(sql_dialect: SQLDialect, mock_db) -> None:
    q = DropIndexQuery(sql_dialect, "posts", database=mock_db, name="idx_old")
    q.name("idx_new").table("comments")
    result = q.to_query_with_params()

    assert result.query == 'DROP INDEX "idx_new"'


def test_sqlite_create_index_if_not_exists(sqlite_dialect: SQLiteDialect, mock_db) -> None:
    q = CreateIndexQuery(sqlite_dialect, "posts", database=mock_db, name="idx_posts_user_id")
    q.columns("user_id").if_not_exists()

    assert q.to_query_with_params().query == 'CREATE INDEX IF NOT EXISTS "idx_posts_user_id" ON "posts" ("user_id")'


def test_pg_create_index_if_not_exists(pg_dialect: PostgresqlDialect, mock_db) -> None:
    q = CreateIndexQuery(pg_dialect, "posts", database=mock_db, name="idx_posts_user_id")
    q.columns("user_id").if_not_exists()

    assert q.to_query_with_params().query == 'CREATE INDEX IF NOT EXISTS "idx_posts_user_id" ON "posts" ("user_id")'


def test_pg_create_index_if_not_exists_unsupported_before_9_5(mock_db) -> None:
    dialect = PostgresqlDialect(version="9.4")
    q = CreateIndexQuery(dialect, "posts", database=mock_db, name="idx_posts_user_id")
    q.columns("user_id").if_not_exists()

    with pytest.raises(QueryError):
        q.to_query_with_params()


def test_mysql_drop_index_names_the_table(mysql_dialect: MySQLDialect, mock_db) -> None:
    q = DropIndexQuery(mysql_dialect, "posts", database=mock_db, name="idx_posts_user_id")

    assert q.to_query_with_params().query == "DROP INDEX `idx_posts_user_id` ON `posts`"


def test_mysql_create_index_if_not_exists_raises(mysql_dialect: MySQLDialect, mock_db) -> None:
    q = CreateIndexQuery(mysql_dialect, "posts", database=mock_db, name="idx_posts_user_id")
    q.columns("user_id").if_not_exists()

    with pytest.raises(QueryError):
        q.to_query_with_params()


def test_mysql_drop_index_if_exists_raises(mysql_dialect: MySQLDialect, mock_db) -> None:
    q = DropIndexQuery(mysql_dialect, "posts", database=mock_db, name="idx_posts_user_id")
    q.if_exists()

    with pytest.raises(QueryError):
        q.to_query_with_params()


def test_mariadb_supports_index_if_exists(mock_db) -> None:
    dialect = MySQLDialect(version="10.11.2", is_mariadb=True)

    create = CreateIndexQuery(dialect, "posts", database=mock_db, name="idx_posts_user_id")
    create.columns("user_id").if_not_exists()
    assert create.to_query_with_params().query == (
        "CREATE INDEX IF NOT EXISTS `idx_posts_user_id` ON `posts` (`user_id`)"
    )

    drop = DropIndexQuery(dialect, "posts", database=mock_db, name="idx_posts_user_id")
    drop.if_exists()
    assert drop.to_query_with_params().query == "DROP INDEX IF EXISTS `idx_posts_user_id` ON `posts`"


def test_mariadb_index_if_exists_unsupported_before_10_1_4(mock_db) -> None:
    dialect = MySQLDialect(version="10.1.3", is_mariadb=True)
    q = DropIndexQuery(dialect, "posts", database=mock_db, name="idx_posts_user_id")
    q.if_exists()

    with pytest.raises(QueryError):
        q.to_query_with_params()
