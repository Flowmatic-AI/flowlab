from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.db._query_with_params import QueryWithParams
from flowlab.modules.db.query._having_mixin import HavingMixin
from flowlab.modules.db.query._joins_mixin import JoinsMixin
from flowlab.modules.db.query._query import SingleQuery
from flowlab.modules.db.query._simple_mixins import (
    ColumnsMixin,
    DistinctMixin,
    GroupByMixin,
    LimitMixin,
    OffsetMixin,
    OrderByMixin,
    UnionMixin,
)
from flowlab.modules.db.query._where_mixin import WhereMixin

if TYPE_CHECKING:
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC
    from flowlab.modules.db.query._order_by import OrderBy
    from flowlab.modules.db.query._union import Union
    from flowlab.modules.db.query.expressions import Alias, SubQuery


class SelectQuery(
    SingleQuery,
    WhereMixin,
    HavingMixin,
    JoinsMixin,
    ColumnsMixin,
    DistinctMixin,
    GroupByMixin,
    OrderByMixin,
    LimitMixin,
    OffsetMixin,
    UnionMixin,
):
    def __init__(self, dialect: DialectABC, table: str | list[str] | Alias | SubQuery, database: DatabaseABC) -> None:
        super().__init__(dialect, table, database)

        self.where: list[Any] = []
        self.having: list[Any] = []
        self.joins: list[Any] = []
        self._columns_list: list[Any] | None = None
        self._distinct: list[Any] | None = None
        self._group_by_cols: list[Any] | None = None
        self._order_by_list: list[OrderBy] | None = None
        self._limit_val: int | None = None
        self._offset_val: int | None = None
        self._unions_list: list[Union] | None = None

    def table(self, table: str | list[str] | Alias | SubQuery) -> Self:
        self._table = table
        return self

    def to_query_with_params(self) -> QueryWithParams:
        return self._dialect.select(
            distinct=self._distinct,
            columns=self._columns_list,
            table=self._table,
            joins=self.joins,
            where=self.where,
            group_by=self._group_by_cols,
            having=self.having,
            order_by=self._order_by_list,
            limit=self._limit_val,
            offset=self._offset_val,
            unions=self._unions_list,
        )

    def count(self, emulate_prepare: bool = False) -> int:
        qwp = self.to_query_with_params()
        count_qwp = QueryWithParams(query=f"SELECT count(*) FROM ({qwp.query}) AS _count", params=qwp.params)
        value = self._run(count_qwp, emulate_prepare).scalar()

        return int(value) if value is not None else 0
