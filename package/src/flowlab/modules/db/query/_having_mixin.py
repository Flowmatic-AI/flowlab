from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.db.query._condition import Condition
from flowlab.modules.db.query._condition_group import ConditionGroupABC
from flowlab.modules.db.query._condition_mixin import ConditionMixin
from flowlab.modules.db.query.enums import ChainEnum

if TYPE_CHECKING:
    from flowlab.modules.db.query._select import SelectQuery
    from flowlab.modules.db.query.expressions import SqlABC


class HavingMixin(ConditionMixin):
    having: list[Any]

    def having_equals(self, column: str | list[str], value: Any, cast: bool = False) -> Self:
        self._equals(self.having, column, value, cast=cast)
        return self

    def or_having_equals(self, column: str | list[str], value: Any, cast: bool = False) -> Self:
        self._equals(self.having, column, value, cast=cast, chain=ChainEnum.OR)
        return self

    def having_not_equals(self, column: str | list[str], value: Any, cast: bool = False) -> Self:
        self._not_equals(self.having, column, value, cast=cast)
        return self

    def or_having_not_equals(self, column: str | list[str], value: Any, cast: bool = False) -> Self:
        self._not_equals(self.having, column, value, cast=cast, chain=ChainEnum.OR)
        return self

    def having_is_null(self, column: str | list[str]) -> Self:
        self._is_null(self.having, column)
        return self

    def or_having_is_null(self, column: str | list[str]) -> Self:
        self._is_null(self.having, column, chain=ChainEnum.OR)
        return self

    def having_is_not_null(self, column: str | list[str]) -> Self:
        self._is_not_null(self.having, column)
        return self

    def or_having_is_not_null(self, column: str | list[str]) -> Self:
        self._is_not_null(self.having, column, chain=ChainEnum.OR)
        return self

    def having_like(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._like(self.having, column, value, case_insensitive)
        return self

    def or_having_like(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._like(self.having, column, value, case_insensitive, chain=ChainEnum.OR)
        return self

    def having_not_like(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._not_like(self.having, column, value, case_insensitive)
        return self

    def or_having_not_like(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._not_like(self.having, column, value, case_insensitive, chain=ChainEnum.OR)
        return self

    def having_starts_with(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._starts_with(self.having, column, value, case_insensitive, escape_backslash)
        return self

    def or_having_starts_with(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._starts_with(self.having, column, value, case_insensitive, escape_backslash, chain=ChainEnum.OR)
        return self

    def having_ends_with(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._ends_with(self.having, column, value, case_insensitive, escape_backslash)
        return self

    def or_having_ends_with(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._ends_with(self.having, column, value, case_insensitive, escape_backslash, chain=ChainEnum.OR)
        return self

    def having_contains(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._contains(self.having, column, value, case_insensitive, escape_backslash)
        return self

    def or_having_contains(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._contains(self.having, column, value, case_insensitive, escape_backslash, chain=ChainEnum.OR)
        return self

    def having_not_contains(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._not_contains(self.having, column, value, case_insensitive, escape_backslash)
        return self

    def or_having_not_contains(
        self, column: str | list[str], value: Any, case_insensitive: bool = False, escape_backslash: bool = False
    ) -> Self:
        self._not_contains(self.having, column, value, case_insensitive, escape_backslash, chain=ChainEnum.OR)
        return self

    def having_glob(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._glob(self.having, column, value, case_insensitive)
        return self

    def or_having_glob(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._glob(self.having, column, value, case_insensitive, chain=ChainEnum.OR)
        return self

    def having_not_glob(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._not_glob(self.having, column, value, case_insensitive)
        return self

    def or_having_not_glob(self, column: str | list[str], value: Any, case_insensitive: bool = False) -> Self:
        self._not_glob(self.having, column, value, case_insensitive, chain=ChainEnum.OR)
        return self

    def having_in(self, column: str | list[str], values: list[Any]) -> Self:
        self._in(self.having, column, values)
        return self

    def or_having_in(self, column: str | list[str], values: list[Any]) -> Self:
        self._in(self.having, column, values, chain=ChainEnum.OR)
        return self

    def having_not_in(self, column: str | list[str], values: list[Any]) -> Self:
        self._not_in(self.having, column, values)
        return self

    def or_having_not_in(self, column: str | list[str], values: list[Any]) -> Self:
        self._not_in(self.having, column, values, chain=ChainEnum.OR)
        return self

    def having_less_than(self, column: str | list[str], value: Any) -> Self:
        self._less_than(self.having, column, value)
        return self

    def or_having_less_than(self, column: str | list[str], value: Any) -> Self:
        self._less_than(self.having, column, value, chain=ChainEnum.OR)
        return self

    def having_less_than_or_equals(self, column: str | list[str], value: Any) -> Self:
        self._less_than_or_equals(self.having, column, value)
        return self

    def or_having_less_than_or_equals(self, column: str | list[str], value: Any) -> Self:
        self._less_than_or_equals(self.having, column, value, chain=ChainEnum.OR)
        return self

    def having_greater_than(self, column: str | list[str], value: Any) -> Self:
        self._greater_than(self.having, column, value)
        return self

    def or_having_greater_than(self, column: str | list[str], value: Any) -> Self:
        self._greater_than(self.having, column, value, chain=ChainEnum.OR)
        return self

    def having_greater_than_or_equals(self, column: str | list[str], value: Any) -> Self:
        self._greater_than_or_equals(self.having, column, value)
        return self

    def or_having_greater_than_or_equals(self, column: str | list[str], value: Any) -> Self:
        self._greater_than_or_equals(self.having, column, value, chain=ChainEnum.OR)
        return self

    def having_between(self, column: str | list[str], min_val: Any, max_val: Any) -> Self:
        self._between(self.having, column, min_val, max_val)
        return self

    def or_having_between(self, column: str | list[str], min_val: Any, max_val: Any) -> Self:
        self._between(self.having, column, min_val, max_val, chain=ChainEnum.OR)
        return self

    def having_not_between(self, column: str | list[str], min_val: Any, max_val: Any) -> Self:
        self._not_between(self.having, column, min_val, max_val)
        return self

    def or_having_not_between(self, column: str | list[str], min_val: Any, max_val: Any) -> Self:
        self._not_between(self.having, column, min_val, max_val, chain=ChainEnum.OR)
        return self

    def having_empty(self, column: str | list[str]) -> Self:
        self._empty(self.having, column)
        return self

    def or_having_empty(self, column: str | list[str]) -> Self:
        self._empty(self.having, column, chain=ChainEnum.OR)
        return self

    def having_not_empty(self, column: str | list[str]) -> Self:
        self._not_empty(self.having, column)
        return self

    def or_having_not_empty(self, column: str | list[str]) -> Self:
        self._not_empty(self.having, column, chain=ChainEnum.OR)
        return self

    def having_regex(self, column: str | list[str], pattern: Any, flags: Any = None) -> Self:
        self._regex(self.having, column, pattern, flags)
        return self

    def or_having_regex(self, column: str | list[str], pattern: Any, flags: Any = None) -> Self:
        self._regex(self.having, column, pattern, flags, chain=ChainEnum.OR)
        return self

    def having_not_regex(self, column: str | list[str], pattern: Any, flags: Any = None) -> Self:
        self._not_regex(self.having, column, pattern, flags)
        return self

    def or_having_not_regex(self, column: str | list[str], pattern: Any, flags: Any = None) -> Self:
        self._not_regex(self.having, column, pattern, flags, chain=ChainEnum.OR)
        return self

    def having_exists(self, select_query: SelectQuery) -> Self:
        self._exists(self.having, select_query)
        return self

    def or_having_exists(self, select_query: SelectQuery) -> Self:
        self._exists(self.having, select_query, chain=ChainEnum.OR)
        return self

    def having_not_exists(self, select_query: SelectQuery) -> Self:
        self._not_exists(self.having, select_query)
        return self

    def or_having_not_exists(self, select_query: SelectQuery) -> Self:
        self._not_exists(self.having, select_query, chain=ChainEnum.OR)
        return self

    def having_group(self, callback: Callable[..., Any]) -> Self:
        self._group(self.having, callback, group_class=HavingGroup)
        return self

    def or_having_group(self, callback: Callable[..., Any]) -> Self:
        self._group(self.having, callback, group_class=HavingGroup, chain=ChainEnum.OR)
        return self

    def having_not_group(self, callback: Callable[..., Any]) -> Self:
        self._group(self.having, callback, not_=True, group_class=HavingGroup)
        return self

    def or_having_not_group(self, callback: Callable[..., Any]) -> Self:
        self._group(self.having, callback, not_=True, group_class=HavingGroup, chain=ChainEnum.OR)
        return self

    def having_operator(self, column: str | list[str] | SqlABC, operator: str, value: Any) -> Self:
        self._operator(self.having, column, operator, value)
        return self

    def or_having_operator(self, column: str | list[str] | SqlABC, operator: str, value: Any) -> Self:
        self._operator(self.having, column, operator, value, chain=ChainEnum.OR)
        return self

    def having_raw(self, sql: str, values: list[Any] | None = None) -> Self:
        self._add_raw_condition(self.having, sql, values)
        return self

    def or_having_raw(self, sql: str, values: list[Any] | None = None) -> Self:
        self._add_raw_condition(self.having, sql, values, chain=ChainEnum.OR)
        return self


class HavingGroup(ConditionGroupABC, HavingMixin):
    def __init__(self, chain: ChainEnum = ChainEnum.AND, not_: bool = False) -> None:
        super().__init__(chain=chain, not_=not_)
        self.having: list[Any] = []

    @property
    def conditions(self) -> list[Condition | ConditionGroupABC]:
        return list(self.having)

    def add_condition(self, condition: Condition | ConditionGroupABC) -> None:
        self.having.append(condition)
