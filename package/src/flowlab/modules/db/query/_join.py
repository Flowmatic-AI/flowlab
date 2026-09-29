from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.db.query._condition import Condition
from flowlab.modules.db.query._condition_group import ConditionGroupABC
from flowlab.modules.db.query._condition_mixin import ConditionMixin
from flowlab.modules.db.query.enums import ChainEnum, JoinEnum
from flowlab.modules.db.query.expressions import Identifier, SqlABC

if TYPE_CHECKING:
    from flowlab.modules.db.query._select import SelectQuery


@dataclass
class Join(ConditionMixin):
    join: JoinEnum
    table: str | list[str] | SqlABC
    conditions: list[Condition | ConditionGroupABC] = field(default_factory=list)

    def where_equals(self, column: str | list[str], value: Any, cast: bool = False) -> Self:
        self._equals(self.conditions, column, value, cast=cast)
        return self

    def or_where_equals(self, column: str | list[str], value: Any, cast: bool = False) -> Self:
        self._equals(self.conditions, column, value, cast=cast, chain=ChainEnum.OR)
        return self

    def where_not_equals(self, column: str | list[str], value: Any, cast: bool = False) -> Self:
        self._not_equals(self.conditions, column, value, cast=cast)
        return self

    def or_where_not_equals(self, column: str | list[str], value: Any, cast: bool = False) -> Self:
        self._not_equals(self.conditions, column, value, cast=cast, chain=ChainEnum.OR)
        return self

    def where_is_null(self, column: str | list[str]) -> Self:
        self._is_null(self.conditions, column)
        return self

    def or_where_is_null(self, column: str | list[str]) -> Self:
        self._is_null(self.conditions, column, chain=ChainEnum.OR)
        return self

    def where_is_not_null(self, column: str | list[str]) -> Self:
        self._is_not_null(self.conditions, column)
        return self

    def or_where_is_not_null(self, column: str | list[str]) -> Self:
        self._is_not_null(self.conditions, column, chain=ChainEnum.OR)
        return self

    def where_like(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._like(self.conditions, column, value, case_insensitive)
        return self

    def or_where_like(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._like(self.conditions, column, value, case_insensitive, chain=ChainEnum.OR)
        return self

    def where_not_like(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._not_like(self.conditions, column, value, case_insensitive)
        return self

    def or_where_not_like(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._not_like(self.conditions, column, value, case_insensitive, chain=ChainEnum.OR)
        return self

    def where_starts_with(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._starts_with(self.conditions, column, value, case_insensitive, escape_backslash)
        return self

    def or_where_starts_with(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._starts_with(self.conditions, column, value, case_insensitive, escape_backslash, chain=ChainEnum.OR)
        return self

    def where_ends_with(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._ends_with(self.conditions, column, value, case_insensitive, escape_backslash)
        return self

    def or_where_ends_with(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._ends_with(self.conditions, column, value, case_insensitive, escape_backslash, chain=ChainEnum.OR)
        return self

    def where_contains(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._contains(self.conditions, column, value, case_insensitive, escape_backslash)
        return self

    def or_where_contains(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._contains(self.conditions, column, value, case_insensitive, escape_backslash, chain=ChainEnum.OR)
        return self

    def where_not_contains(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._not_contains(self.conditions, column, value, case_insensitive, escape_backslash)
        return self

    def or_where_not_contains(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._not_contains(self.conditions, column, value, case_insensitive, escape_backslash, chain=ChainEnum.OR)
        return self

    def where_glob(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._glob(self.conditions, column, value, case_insensitive)
        return self

    def or_where_glob(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._glob(self.conditions, column, value, case_insensitive, chain=ChainEnum.OR)
        return self

    def where_not_glob(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._not_glob(self.conditions, column, value, case_insensitive)
        return self

    def or_where_not_glob(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._not_glob(self.conditions, column, value, case_insensitive, chain=ChainEnum.OR)
        return self

    def where_in(self, column: str | list[str], values: list[Any]) -> Self:
        self._in(self.conditions, column, values)
        return self

    def or_where_in(self, column: str | list[str], values: list[Any]) -> Self:
        self._in(self.conditions, column, values, chain=ChainEnum.OR)
        return self

    def where_not_in(self, column: str | list[str], values: list[Any]) -> Self:
        self._not_in(self.conditions, column, values)
        return self

    def or_where_not_in(self, column: str | list[str], values: list[Any]) -> Self:
        self._not_in(self.conditions, column, values, chain=ChainEnum.OR)
        return self

    def where_less_than(self, column: str | list[str], value: Any) -> Self:
        self._less_than(self.conditions, column, value)
        return self

    def or_where_less_than(self, column: str | list[str], value: Any) -> Self:
        self._less_than(self.conditions, column, value, chain=ChainEnum.OR)
        return self

    def where_less_than_or_equals(self, column: str | list[str], value: Any) -> Self:
        self._less_than_or_equals(self.conditions, column, value)
        return self

    def or_where_less_than_or_equals(self, column: str | list[str], value: Any) -> Self:
        self._less_than_or_equals(self.conditions, column, value, chain=ChainEnum.OR)
        return self

    def where_greater_than(self, column: str | list[str], value: Any) -> Self:
        self._greater_than(self.conditions, column, value)
        return self

    def or_where_greater_than(self, column: str | list[str], value: Any) -> Self:
        self._greater_than(self.conditions, column, value, chain=ChainEnum.OR)
        return self

    def where_greater_than_or_equals(self, column: str | list[str], value: Any) -> Self:
        self._greater_than_or_equals(self.conditions, column, value)
        return self

    def or_where_greater_than_or_equals(self, column: str | list[str], value: Any) -> Self:
        self._greater_than_or_equals(self.conditions, column, value, chain=ChainEnum.OR)
        return self

    def where_between(self, column: str | list[str], min_val: Any, max_val: Any) -> Self:
        self._between(self.conditions, column, min_val, max_val)
        return self

    def or_where_between(self, column: str | list[str], min_val: Any, max_val: Any) -> Self:
        self._between(self.conditions, column, min_val, max_val, chain=ChainEnum.OR)
        return self

    def where_not_between(self, column: str | list[str], min_val: Any, max_val: Any) -> Self:
        self._not_between(self.conditions, column, min_val, max_val)
        return self

    def or_where_not_between(self, column: str | list[str], min_val: Any, max_val: Any) -> Self:
        self._not_between(self.conditions, column, min_val, max_val, chain=ChainEnum.OR)
        return self

    def where_empty(self, column: str | list[str]) -> Self:
        self._empty(self.conditions, column)
        return self

    def or_where_empty(self, column: str | list[str]) -> Self:
        self._empty(self.conditions, column, chain=ChainEnum.OR)
        return self

    def where_not_empty(self, column: str | list[str]) -> Self:
        self._not_empty(self.conditions, column)
        return self

    def or_where_not_empty(self, column: str | list[str]) -> Self:
        self._not_empty(self.conditions, column, chain=ChainEnum.OR)
        return self

    def where_regex(self, column: str | list[str], pattern: Any, flags: Any = None) -> Self:
        self._regex(self.conditions, column, pattern, flags)
        return self

    def or_where_regex(self, column: str | list[str], pattern: Any, flags: Any = None) -> Self:
        self._regex(self.conditions, column, pattern, flags, chain=ChainEnum.OR)
        return self

    def where_not_regex(self, column: str | list[str], pattern: Any, flags: Any = None) -> Self:
        self._not_regex(self.conditions, column, pattern, flags)
        return self

    def or_where_not_regex(self, column: str | list[str], pattern: Any, flags: Any = None) -> Self:
        self._not_regex(self.conditions, column, pattern, flags, chain=ChainEnum.OR)
        return self

    def where_exists(self, select_query: SelectQuery) -> Self:
        self._exists(self.conditions, select_query)
        return self

    def or_where_exists(self, select_query: SelectQuery) -> Self:
        self._exists(self.conditions, select_query, chain=ChainEnum.OR)
        return self

    def where_not_exists(self, select_query: SelectQuery) -> Self:
        self._not_exists(self.conditions, select_query)
        return self

    def or_where_not_exists(self, select_query: SelectQuery) -> Self:
        self._not_exists(self.conditions, select_query, chain=ChainEnum.OR)
        return self

    def where_group(self, callback: Callable[..., Any]) -> Self:
        from flowlab.modules.db.query._where_mixin import WhereGroup

        self._group(self.conditions, callback, group_class=WhereGroup)
        return self

    def or_where_group(self, callback: Callable[..., Any]) -> Self:
        from flowlab.modules.db.query._where_mixin import WhereGroup

        self._group(self.conditions, callback, group_class=WhereGroup, chain=ChainEnum.OR)
        return self

    def where_not_group(self, callback: Callable[..., Any]) -> Self:
        from flowlab.modules.db.query._where_mixin import WhereGroup

        self._group(self.conditions, callback, not_=True, group_class=WhereGroup)
        return self

    def or_where_not_group(self, callback: Callable[..., Any]) -> Self:
        from flowlab.modules.db.query._where_mixin import WhereGroup

        self._group(self.conditions, callback, not_=True, group_class=WhereGroup, chain=ChainEnum.OR)
        return self

    def where_operator(self, column: str | list[str] | SqlABC, operator: str, value: Any) -> Self:
        self._operator(self.conditions, column, operator, value)
        return self

    def or_where_operator(self, column: str | list[str] | SqlABC, operator: str, value: Any) -> Self:
        self._operator(self.conditions, column, operator, value, chain=ChainEnum.OR)
        return self

    def where_raw(self, sql: str, values: list[Any] | None = None) -> Self:
        self._add_raw_condition(self.conditions, sql, values)
        return self

    def or_where_raw(self, sql: str, values: list[Any] | None = None) -> Self:
        self._add_raw_condition(self.conditions, sql, values, chain=ChainEnum.OR)
        return self

    def on(self, left: list[str], right: list[str]) -> Self:
        self._equals(self.conditions, left, Identifier(right))
        return self

    def or_on(self, left: list[str], right: list[str]) -> Self:
        self._equals(self.conditions, left, Identifier(right), chain=ChainEnum.OR)
        return self
