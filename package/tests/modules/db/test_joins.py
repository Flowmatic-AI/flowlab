from __future__ import annotations

from typing import Any

from flowlab.modules.db.dialects import SQLDialect
from flowlab.modules.db.query import Join, SelectQuery
from flowlab.modules.db.query.enums import ChainEnum, JoinEnum
from flowlab.modules.db.query.expressions import Alias


def test_join_creation() -> None:
    j = Join(join=JoinEnum.LEFT_JOIN, table="posts")
    assert j.join == JoinEnum.LEFT_JOIN
    assert j.table == "posts"
    assert j.conditions == []


def test_join_on_condition() -> None:
    j = Join(join=JoinEnum.INNER_JOIN, table="posts")
    j.on("users.id", "posts.user_id")
    assert len(j.conditions) == 1
    assert j.conditions[0].chain == ChainEnum.AND


def test_join_or_on_condition() -> None:
    j = Join(join=JoinEnum.LEFT_JOIN, table="posts")
    j.or_on("a", "b")
    assert j.conditions[0].chain == ChainEnum.OR


def test_multiple_join_conditions() -> None:
    j = Join(join=JoinEnum.LEFT_JOIN, table="posts")
    j.on("users.id", "posts.user_id")
    j.on("users.deleted", 0)
    assert len(j.conditions) == 2


def test_all_join_types() -> None:
    for join_type in JoinEnum:
        j = Join(join=join_type, table="t")
        assert j.join == join_type


def test_join_returns_query_for_chaining(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    returned = q.inner_join("posts").left_join("comments").where_equals("active", 1)
    assert returned is q
    assert [j.join for j in q.joins] == [JoinEnum.INNER_JOIN, JoinEnum.LEFT_JOIN]


def test_join_callback_receives_join(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.inner_join("posts", lambda join: join.on(["users", "id"], ["posts", "user_id"]))
    assert len(q.joins) == 1
    assert len(q.joins[0].conditions) == 1


def test_join_callback_returning_none_keeps_join(sql_dialect: SQLDialect, mock_db) -> None:
    def on(join: Join) -> None:
        join.on(["users", "id"], ["posts", "user_id"])

    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.inner_join("posts", on)
    assert len(q.joins) == 1
    assert len(q.joins[0].conditions) == 1


def test_join_callback_returning_non_join_cancels_join(sql_dialect: SQLDialect, mock_db) -> None:
    def on(join: Join) -> Any:
        return False

    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.inner_join("posts", on)
    assert q.joins == []


def test_join_table_alias_wraps_table(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.left_join_table("posts", None, "p")
    assert isinstance(q.joins[0].table, Alias)
