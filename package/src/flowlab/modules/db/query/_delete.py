from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.db.query._query import SingleQuery
from flowlab.modules.db.query._simple_mixins import ReturningMixin
from flowlab.modules.db.query._where_mixin import WhereMixin

if TYPE_CHECKING:
    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC


class DeleteQuery(SingleQuery, WhereMixin, ReturningMixin):
    def __init__(self, dialect: DialectABC, table: str | list[str], database: DatabaseABC) -> None:
        super().__init__(dialect, table, database)

        self.where: list[Any] = []
        self._returning_list: list[Any] | None = None

    def table(self, table: str | list[str]) -> Self:
        self._table = table
        return self

    def to_query_with_params(self) -> QueryWithParams:
        return self._dialect.delete(
            table=self._table,
            where=self.where,
            returning=self._returning_list,
        )
