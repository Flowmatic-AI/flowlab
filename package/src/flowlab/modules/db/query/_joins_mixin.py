from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.db.query._join import Join
from flowlab.modules.db.query.enums import JoinEnum
from flowlab.modules.db.query.expressions import Alias, SqlABC, SubQuery

if TYPE_CHECKING:
    from flowlab.modules.db.query._select import SelectQuery


class JoinsMixin:
    joins: list[Any]

    def left_join(self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None) -> Self:
        return self._add_join(JoinEnum.LEFT_JOIN, table, on)

    def left_join_table(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None, alias: str | None = None
    ) -> Self:
        return self.left_join(Alias(table, alias) if alias else table, on)

    def left_join_sub_query(
        self, query: SelectQuery, alias: str, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self.left_join(SubQuery(query, alias), on)

    def left_join_lateral(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self._add_join(JoinEnum.LEFT_JOIN_LATERAL, table, on)

    def left_join_lateral_table(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None, alias: str | None = None
    ) -> Self:
        return self.left_join_lateral(Alias(table, alias) if alias else table, on)

    def left_join_lateral_sub_query(
        self, query: SelectQuery, alias: str, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self.left_join_lateral(SubQuery(query, alias), on)

    def inner_join(self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None) -> Self:
        return self._add_join(JoinEnum.INNER_JOIN, table, on)

    def inner_join_table(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None, alias: str | None = None
    ) -> Self:
        return self.inner_join(Alias(table, alias) if alias else table, on)

    def inner_join_sub_query(
        self, query: SelectQuery, alias: str, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self.inner_join(SubQuery(query, alias), on)

    def inner_join_lateral(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self._add_join(JoinEnum.INNER_JOIN_LATERAL, table, on)

    def inner_join_lateral_table(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None, alias: str | None = None
    ) -> Self:
        return self.inner_join_lateral(Alias(table, alias) if alias else table, on)

    def inner_join_lateral_sub_query(
        self, query: SelectQuery, alias: str, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self.inner_join_lateral(SubQuery(query, alias), on)

    def cross_join(self, table: str | list[str] | SqlABC) -> Self:
        return self._add_join(JoinEnum.CROSS_JOIN, table, None)

    def cross_join_table(self, table: str | list[str] | SqlABC, alias: str | None = None) -> Self:
        return self.cross_join(Alias(table, alias) if alias else table)

    def cross_join_sub_query(self, query: SelectQuery, alias: str) -> Self:
        return self.cross_join(SubQuery(query, alias))

    def cross_join_lateral(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self._add_join(JoinEnum.CROSS_JOIN_LATERAL, table, on)

    def cross_join_lateral_table(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None, alias: str | None = None
    ) -> Self:
        return self.cross_join_lateral(Alias(table, alias) if alias else table, on)

    def cross_join_lateral_sub_query(
        self, query: SelectQuery, alias: str, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self.cross_join_lateral(SubQuery(query, alias), on)

    def outer_apply(self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None) -> Self:
        return self._add_join(JoinEnum.LEFT_JOIN_LATERAL, table, on)

    def outer_apply_table(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None, alias: str | None = None
    ) -> Self:
        return self.outer_apply(Alias(table, alias) if alias else table, on)

    def outer_apply_sub_query(
        self, query: SelectQuery, alias: str, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self.outer_apply(SubQuery(query, alias), on)

    def cross_apply(self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None) -> Self:
        return self._add_join(JoinEnum.INNER_JOIN_LATERAL, table, on)

    def cross_apply_table(
        self, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None = None, alias: str | None = None
    ) -> Self:
        return self.cross_apply(Alias(table, alias) if alias else table, on)

    def cross_apply_sub_query(
        self, query: SelectQuery, alias: str, on: Callable[[Join], Join | None] | None = None
    ) -> Self:
        return self.cross_apply(SubQuery(query, alias), on)

    def join(self, sql: Any) -> Self:
        self.joins.append(sql)
        return self

    def _add_join(
        self, join_type: JoinEnum, table: str | list[str] | SqlABC, on: Callable[[Join], Join | None] | None
    ) -> Self:
        join: Any = Join(join=join_type, table=table)

        if on:
            returned = on(join)
            if returned is not None:
                join = returned

        if not isinstance(join, Join):
            return self

        self.joins.append(join)

        return self
