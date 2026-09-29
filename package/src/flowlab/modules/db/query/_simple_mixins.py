from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.db.query._on_conflict import OnConflict
from flowlab.modules.db.query._order_by import OrderBy
from flowlab.modules.db.query._union import Union
from flowlab.modules.db.query.enums import OrderByDirectionEnum

if TYPE_CHECKING:
    from flowlab.modules.db.query._select import SelectQuery
    from flowlab.modules.db.query.expressions import SqlABC


class ColumnsMixin:
    _columns_list: list[Any] | None

    def columns(self, cols: list[Any] | dict[str, Any]) -> Self:
        from flowlab.modules.db.query._select import SelectQuery
        from flowlab.modules.db.query.expressions import Alias, SubQuery

        items = cols.items() if isinstance(cols, dict) else enumerate(cols)

        result: list[Any] = []

        for key, column in items:
            is_numeric_key = isinstance(key, int) or (isinstance(key, str) and key.isdigit())

            if isinstance(column, (Alias, SubQuery)) or is_numeric_key:
                result.append(column)
            elif isinstance(column, SelectQuery):
                result.append(SubQuery(column, str(key)))
            else:
                result.append(Alias(column, str(key)))

        self._columns_list = result

        return self


class DistinctMixin:
    _distinct: list[Any] | None

    def distinct(self, on: list[Any] | None = None) -> Self:
        self._distinct = on if on is not None else []
        return self


class GroupByMixin:
    _group_by_cols: list[Any] | None

    def group_by(self, columns: list[Any]) -> Self:
        self._group_by_cols = columns
        return self


class OrderByMixin:
    _order_by_list: list[OrderBy] | None

    def order_by_asc(self, column: str | list[str] | SqlABC) -> Self:
        if self._order_by_list is None:
            self._order_by_list = []
        self._order_by_list.append(OrderBy(column=column, direction=OrderByDirectionEnum.ASC))
        return self

    def order_by_desc(self, column: str | list[str] | SqlABC) -> Self:
        if self._order_by_list is None:
            self._order_by_list = []
        self._order_by_list.append(OrderBy(column=column, direction=OrderByDirectionEnum.DESC))
        return self


class LimitMixin:
    _limit_val: int | None

    def limit(self, limit: int) -> Self:
        self._limit_val = limit if limit >= 0 else None
        return self


class OffsetMixin:
    _offset_val: int | None

    def offset(self, offset: int) -> Self:
        self._offset_val = offset if offset > 0 else None
        return self


class UnionMixin:
    _unions_list: list[Union] | None

    def union(self, select_query: SelectQuery) -> Self:
        from flowlab.modules.db.query.enums import UnionEnum

        if self._unions_list is None:
            self._unions_list = []
        self._unions_list.append(Union(union=UnionEnum.UNION, select_query=select_query))
        return self

    def union_all(self, select_query: SelectQuery) -> Self:
        from flowlab.modules.db.query.enums import UnionEnum

        if self._unions_list is None:
            self._unions_list = []
        self._unions_list.append(Union(union=UnionEnum.UNION_ALL, select_query=select_query))
        return self


class ValuesMixin:
    _values_list: list[dict[str, Any]]

    def values(self, *dicts: dict[str, Any]) -> Self:
        self._values_list.extend(dicts)
        return self


class UpdatesMixin:
    _updates_dict: dict[str, Any]

    def set(self, updates: dict[str, Any]) -> Self:
        return self.updates(updates)

    def updates(self, updates: dict[str, Any]) -> Self:
        self._updates_dict = dict(updates)
        return self


class ReturningMixin:
    _returning_list: list[Any] | None

    def returning(self, columns: list[Any] | None = None) -> Self:
        self._returning_list = columns if columns is not None else []
        return self


class OnConflictMixin:
    _on_conflict: OnConflict | None

    def on_conflict_do_nothing(self, conflict: str | list[str]) -> Self:
        self._on_conflict = OnConflict(conflict=conflict, updates=None)
        return self

    def on_conflict_do_update(self, conflict: str | list[str], updates: dict[str, Any] | None = None) -> Self:
        self._on_conflict = OnConflict(conflict=conflict, updates=updates if updates is not None else {})
        return self

    def insert_ignore(self, conflict: str | list[str]) -> Self:
        return self.on_conflict_do_nothing(conflict)

    def on_duplicate_key_update(self, conflict: str | list[str], updates: dict[str, Any] | None = None) -> Self:
        return self.on_conflict_do_update(conflict, updates)


class LastInsertIdMixin:
    _last_insert_id_col: str | None

    def last_insert_id(self, column: str) -> Self:
        self._last_insert_id_col = column
        return self
