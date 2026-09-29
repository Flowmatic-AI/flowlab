from __future__ import annotations

from flowlab.modules.db.dialects import SQLDialect
from flowlab.modules.db.query import HavingGroup, Join, SelectQuery, WhereGroup
from flowlab.modules.db.query.enums import ChainEnum, ConditionEnum, JoinEnum


def test_where_group_has_full_condition_api() -> None:
    group = WhereGroup()
    group.where_between("age", 1, 10).where_like("name", "%a%").where_regex("email", "^a").where_not_glob("f", "*.txt")
    assert len(group.conditions) == 4


def test_having_group_has_full_condition_api() -> None:
    group = HavingGroup()
    group.having_greater_than("count", 5).having_between("count", 1, 10).having_like("name", "x")
    assert len(group.conditions) == 3


def test_where_group_nested_in_select(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.where_group(
        lambda g: g.where_like("name", "%a%").or_where_starts_with("name", "B").where_not_between("age", 1, 2)
    )
    qwp = q.to_query_with_params()
    assert "LIKE" in qwp.query
    assert "NOT" in qwp.query


def test_where_empty_builds_null_or_zero_or_blank_group() -> None:
    group = WhereGroup()
    group.where_empty("name")
    assert len(group.conditions) == 1
    inner = group.conditions[0]
    assert isinstance(inner, WhereGroup)
    assert len(inner.conditions) == 3
    c0, c1, c2 = inner.conditions
    assert c0.condition == ConditionEnum.EQUALS and c0.value is None and c0.chain == ChainEnum.AND
    assert c1.condition == ConditionEnum.EQUALS and c1.value == 0 and c1.chain == ChainEnum.OR
    assert c2.condition == ConditionEnum.EQUALS and c2.value == "" and c2.cast is True and c2.chain == ChainEnum.OR


def test_where_not_empty_builds_not_null_and_group() -> None:
    group = WhereGroup()
    group.where_not_empty("name")
    inner = group.conditions[0]
    assert isinstance(inner, WhereGroup)
    c0, c1, c2 = inner.conditions
    assert c0.condition == ConditionEnum.NOT_EQUALS and c0.value is None and c0.chain == ChainEnum.AND
    assert c1.condition == ConditionEnum.NOT_EQUALS and c1.value == 0 and c1.chain == ChainEnum.AND
    assert c2.condition == ConditionEnum.NOT_EQUALS and c2.value == "" and c2.cast is True and c2.chain == ChainEnum.AND


def test_having_empty_builds_group_too() -> None:
    group = HavingGroup()
    group.having_empty("count")
    inner = group.conditions[0]
    assert len(inner.conditions) == 3


def test_or_where_empty_chains_with_or_not_and() -> None:
    group = WhereGroup()
    group.where_equals("a", 1)
    group.or_where_empty("name")
    assert group.conditions[1].chain == ChainEnum.OR


def test_or_where_not_empty_chains_with_or_not_and() -> None:
    group = WhereGroup()
    group.where_equals("a", 1)
    group.or_where_not_empty("name")
    assert group.conditions[1].chain == ChainEnum.OR


def test_or_having_empty_chains_with_or_not_and() -> None:
    group = HavingGroup()
    group.having_equals("a", 1)
    group.or_having_empty("count")
    assert group.conditions[1].chain == ChainEnum.OR


def test_or_having_not_empty_chains_with_or_not_and() -> None:
    group = HavingGroup()
    group.having_equals("a", 1)
    group.or_having_not_empty("count")
    assert group.conditions[1].chain == ChainEnum.OR


def test_where_group_with_no_conditions_added_is_dropped() -> None:
    group = WhereGroup()
    group.where_equals("a", 1)
    group.where_group(lambda g: g)
    assert len(group.conditions) == 1


def test_where_equals_cast_param_is_threaded_through() -> None:
    group = WhereGroup()
    group.where_equals("a", "b", cast=True)
    assert group.conditions[0].cast is True


def test_where_like_case_insensitive_param_is_threaded_through() -> None:
    group = WhereGroup()
    group.where_like("name", "a", case_insensitive=True)
    assert group.conditions[0].case_insensitive is True


def test_where_starts_with_case_insensitive_and_escape_backslash() -> None:
    group = WhereGroup()
    group.where_starts_with("name", "a", case_insensitive=True, escape_backslash=True)
    cond = group.conditions[0]
    assert cond.case_insensitive is True
    assert cond.value == "a%"


def test_where_regex_flags_are_threaded_through() -> None:
    group = WhereGroup()
    group.where_regex("email", "^a", flags="i")
    assert group.conditions[0].flags == "i"


def test_escape_like_chars_escapes_glob_style_chars() -> None:
    group = WhereGroup()
    group.where_starts_with("name", "a-b^c[d]e")
    cond = group.conditions[0]
    assert cond.value == "a\\-b\\^c\\[d\\]e%"


def test_having_glob_appends_to_having_not_where() -> None:
    group = HavingGroup()
    group.having_glob("name", "a*")
    assert len(group.conditions) == 1
    assert group.conditions[0].condition == ConditionEnum.GLOB


def test_join_where_like_case_insensitive() -> None:
    j = Join(join=JoinEnum.INNER_JOIN, table="posts")
    j.where_like("title", "a", case_insensitive=True)
    assert j.conditions[0].case_insensitive is True


def test_join_or_where_empty_chains_with_or_not_and() -> None:
    j = Join(join=JoinEnum.INNER_JOIN, table="posts")
    j.where_equals("a", 1)
    j.or_where_empty("title")
    assert j.conditions[1].chain == ChainEnum.OR


def test_join_or_where_not_empty_chains_with_or_not_and() -> None:
    j = Join(join=JoinEnum.INNER_JOIN, table="posts")
    j.where_equals("a", 1)
    j.or_where_not_empty("title")
    assert j.conditions[1].chain == ChainEnum.OR


def test_select_has_full_join_api(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    assert q.inner_join_table("posts") is q
    assert q.cross_join_table("posts") is q
    assert q.left_join_lateral("posts") is q
    assert q.inner_join_lateral("posts") is q
    assert q.cross_join_lateral("posts") is q
    assert q.outer_apply("posts") is q
    assert q.cross_apply("posts") is q
    assert len(q.joins) == 7
    assert all(isinstance(j, Join) for j in q.joins)


def test_outer_apply_maps_to_left_join_lateral(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.outer_apply("posts")
    assert q.joins[0].join == JoinEnum.LEFT_JOIN_LATERAL


def test_cross_apply_maps_to_inner_join_lateral(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.cross_apply("posts")
    assert q.joins[0].join == JoinEnum.INNER_JOIN_LATERAL


def test_left_join_lateral_takes_raw_table_not_subquery_only(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.left_join_lateral_table("posts", alias="p")
    assert q.joins[0].join == JoinEnum.LEFT_JOIN_LATERAL


def test_left_join_lateral_sub_query_still_available(sql_dialect: SQLDialect, mock_db) -> None:
    inner = SelectQuery(sql_dialect, "posts", database=mock_db)
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.left_join_lateral_sub_query(inner, "p")
    assert q.joins[0].join == JoinEnum.LEFT_JOIN_LATERAL


def test_inner_join_sub_query_and_cross_join_sub_query_exist(sql_dialect: SQLDialect, mock_db) -> None:
    inner = SelectQuery(sql_dialect, "posts", database=mock_db)
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    assert q.inner_join_sub_query(inner, "p") is q
    assert q.cross_join_sub_query(inner, "p") is q
    assert [j.join for j in q.joins] == [JoinEnum.INNER_JOIN, JoinEnum.CROSS_JOIN]
