from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query._condition import Condition
from flowlab.modules.db.query._condition_group import ConditionGroupABC
from flowlab.modules.db.query.enums import ChainEnum, ConditionEnum

if TYPE_CHECKING:
    from flowlab.modules.db.query._select import SelectQuery
    from flowlab.modules.db.query.expressions import SqlABC


def _escape_like_chars(string: str, escape_backslash: bool = False) -> str:
    chars = ["\\", "%", "_", "-", "^", "[", "]"] if escape_backslash else ["%", "_", "-", "^", "[", "]"]
    result = string
    for char in chars:
        result = result.replace(char, f"\\{char}")
    return result


class ConditionMixin:
    def _equals(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        cast: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.EQUALS, column, value, chain, cast=cast)

    def _not_equals(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        cast: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.NOT_EQUALS, column, value, chain, cast=cast)

    def _is_null(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.EQUALS, column, None, chain)

    def _is_not_null(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.NOT_EQUALS, column, None, chain)

    def _like(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        case_insensitive: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(
            conditions, ConditionEnum.LIKE, column, value, chain, case_insensitive=case_insensitive
        )

    def _not_like(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        case_insensitive: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(
            conditions, ConditionEnum.NOT_LIKE, column, value, chain, case_insensitive=case_insensitive
        )

    def _starts_with(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        case_insensitive: bool = False,
        escape_backslash: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        val = _escape_like_chars(str(value), escape_backslash)
        return self._like(conditions, column, f"{val}%", case_insensitive, chain)

    def _ends_with(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        case_insensitive: bool = False,
        escape_backslash: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        val = _escape_like_chars(str(value), escape_backslash)
        return self._like(conditions, column, f"%{val}", case_insensitive, chain)

    def _contains(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        case_insensitive: bool = False,
        escape_backslash: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        val = _escape_like_chars(str(value), escape_backslash)
        return self._like(conditions, column, f"%{val}%", case_insensitive, chain)

    def _not_contains(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        case_insensitive: bool = False,
        escape_backslash: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        val = _escape_like_chars(str(value), escape_backslash)
        return self._not_like(conditions, column, f"%{val}%", case_insensitive, chain)

    def _glob(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        case_insensitive: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(
            conditions, ConditionEnum.GLOB, column, value, chain, case_insensitive=case_insensitive
        )

    def _not_glob(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        case_insensitive: bool = False,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(
            conditions, ConditionEnum.NOT_GLOB, column, value, chain, case_insensitive=case_insensitive
        )

    def _in(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        values: list[Any],
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.IN, column, values, chain)

    def _not_in(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        values: list[Any],
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.NOT_IN, column, values, chain)

    def _less_than(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.LESS_THAN, column, value, chain)

    def _less_than_or_equals(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.LESS_THAN_OR_EQUALS, column, value, chain)

    def _greater_than(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.GREATER_THAN, column, value, chain)

    def _greater_than_or_equals(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        value: Any,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.GREATER_THAN_OR_EQUALS, column, value, chain)

    def _between(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        min_val: Any,
        max_val: Any,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.BETWEEN, column, [min_val, max_val], chain)

    def _not_between(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        min_val: Any,
        max_val: Any,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.NOT_BETWEEN, column, [min_val, max_val], chain)

    def _empty(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        chain: ChainEnum = ChainEnum.AND,
    ) -> ConditionGroupABC:
        def build(group: Any) -> Any:
            group.where_is_null(column)
            group.or_where_equals(column, 0)
            group.or_where_equals(column, "", cast=True)
            return group

        return self._group(conditions, build, False, _where_group_class(), chain)

    def _not_empty(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        chain: ChainEnum = ChainEnum.AND,
    ) -> ConditionGroupABC:
        def build(group: Any) -> Any:
            group.where_is_not_null(column)
            group.where_not_equals(column, 0)
            group.where_not_equals(column, "", cast=True)
            return group

        return self._group(conditions, build, False, _where_group_class(), chain)

    def _regex(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        pattern: Any,
        flags: Any = None,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.REGEX, column, pattern, chain, flags=flags)

    def _not_regex(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | None,
        pattern: Any,
        flags: Any = None,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.NOT_REGEX, column, pattern, chain, flags=flags)

    def _exists(
        self,
        conditions: list[Condition | ConditionGroupABC],
        select_query: SelectQuery,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.EXISTS, None, select_query, chain)

    def _not_exists(
        self,
        conditions: list[Condition | ConditionGroupABC],
        select_query: SelectQuery,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, ConditionEnum.NOT_EXISTS, None, select_query, chain)

    def _group(
        self,
        conditions: list[Condition | ConditionGroupABC],
        callback: Callable[..., Any],
        not_: bool = False,
        group_class: type[ConditionGroupABC] | None = None,
        chain: ChainEnum = ChainEnum.AND,
    ) -> ConditionGroupABC:
        if group_class is None:
            group_class = _where_group_class()
        group = group_class(chain=chain, not_=not_)
        result = callback(group)
        if result is not None:
            group = result
        if isinstance(group, ConditionGroupABC) and len(group.conditions) > 0:
            self._add_condition_group(conditions, group)
        return group

    def _operator(
        self,
        conditions: list[Condition | ConditionGroupABC],
        column: str | list[str] | SqlABC | None,
        operator: str,
        value: Any,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        return self._add_condition(conditions, operator, column, value, chain)

    def _add_condition(
        self,
        conditions: list[Condition | ConditionGroupABC],
        condition: Any,
        identifier: str | list[str] | SqlABC | None,
        value: Any,
        chain: ChainEnum = ChainEnum.AND,
        cast: bool = False,
        case_insensitive: bool = False,
        flags: Any = None,
    ) -> Condition:
        cond = Condition(
            condition=condition,
            identifier=identifier,
            value=value,
            chain=chain,
            cast=cast,
            case_insensitive=case_insensitive,
            flags=flags,
        )
        conditions.append(cond)
        return cond

    def _add_condition_group(self, conditions: list[Condition | ConditionGroupABC], group: Any) -> None:
        conditions.append(group)

    def _add_raw_condition(
        self,
        conditions: list[Condition | ConditionGroupABC],
        sql: str,
        values: list[Any] | None = None,
        chain: ChainEnum = ChainEnum.AND,
    ) -> Condition:
        from flowlab.modules.db.query.expressions import Expression

        if values:
            cond = Condition(condition=ConditionEnum.RAW, identifier=None, value=Expression(sql, values), chain=chain)
        else:
            from flowlab.modules.db.query.expressions import Raw

            cond = Condition(condition=ConditionEnum.RAW, identifier=None, value=Raw(sql), chain=chain)
        conditions.append(cond)
        return cond


def _where_group_class() -> type[ConditionGroupABC]:
    from flowlab.modules.db.query._where_mixin import WhereGroup

    return WhereGroup
