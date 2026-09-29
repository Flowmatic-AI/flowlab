from __future__ import annotations

from flowlab.modules.db import QueryWithParams
from flowlab.modules.db.dialects import SQLDialect
from flowlab.modules.db.query import SelectQuery


def test_select_query_creation(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.columns(["id", "name"])
    qwp: QueryWithParams = q.to_query_with_params()
    assert qwp.query == 'SELECT "id", "name" FROM "users"'


def test_select_with_where(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.columns(["id", "name"])
    q.where_equals("id", 1)
    qwp: QueryWithParams = q.to_query_with_params()
    assert "WHERE" in qwp.query
    assert qwp.params == [1]


def test_select_with_multiple_conditions(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.where_equals("name", "John")
    q.or_where_equals("name", "Jane")
    qwp: QueryWithParams = q.to_query_with_params()
    assert "OR" in qwp.query or "AND" in qwp.query


def test_select_with_limit(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.limit(10)
    qwp: QueryWithParams = q.to_query_with_params()
    assert "LIMIT 10" in qwp.query


def test_select_with_offset(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.limit(10)
    q.offset(20)
    qwp: QueryWithParams = q.to_query_with_params()
    assert "LIMIT 10" in qwp.query
    assert "OFFSET 20" in qwp.query


def test_select_with_order_by(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.order_by_asc("name")
    qwp: QueryWithParams = q.to_query_with_params()
    assert "ORDER BY" in qwp.query
    assert "ASC" in qwp.query


def test_select_with_order_by_desc(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.order_by_desc("name")
    qwp: QueryWithParams = q.to_query_with_params()
    assert "DESC" in qwp.query


def test_select_where_between(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.where_between("age", 18, 65)
    qwp: QueryWithParams = q.to_query_with_params()
    assert "BETWEEN" in qwp.query


def test_select_where_in(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.where_in("id", [1, 2, 3])
    qwp: QueryWithParams = q.to_query_with_params()
    assert "IN" in qwp.query


def test_select_where_like(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.where_like("name", "%john%")
    qwp: QueryWithParams = q.to_query_with_params()
    assert "LIKE" in qwp.query


def test_select_where_is_null(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.where_is_null("deleted_at")
    qwp: QueryWithParams = q.to_query_with_params()
    assert "IS NULL" in qwp.query


def test_select_to_sql(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.columns(["id"])
    q.where_equals("id", 1)
    sql: str = q.to_sql()
    assert '"id"' in sql
    assert '"users"' in sql


def test_select_where_group(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.where_group(lambda g: g.where_equals("name", "John").or_where_equals("name", "Jane"))
    qwp: QueryWithParams = q.to_query_with_params()
    assert "(" in qwp.query
    assert ")" in qwp.query


def test_select_join(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.left_join("posts", lambda join: join.on("users.id", "posts.user_id"))
    qwp: QueryWithParams = q.to_query_with_params()
    assert "LEFT JOIN" in qwp.query


def test_select_columns_qualified_lists(sql_dialect: SQLDialect, mock_db) -> None:
    """A two-element list is a qualified column, not a value to stringify --
    columns() has to escape it segment by segment like the where_* family."""
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.columns([["users", "email"], "name"])
    qwp: QueryWithParams = q.to_query_with_params()
    assert qwp.query == 'SELECT "users"."email", "name" FROM "users"'


def test_select_columns_qualified_list_with_alias(sql_dialect: SQLDialect, mock_db) -> None:
    q: SelectQuery = SelectQuery(sql_dialect, "users", database=mock_db)
    q.columns({"mail": ["users", "email"]})
    qwp: QueryWithParams = q.to_query_with_params()
    assert qwp.query == 'SELECT "users"."email" AS "mail" FROM "users"'
