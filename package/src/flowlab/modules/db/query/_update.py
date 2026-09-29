from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query._query import SingleQuery
from flowlab.modules.db.query._simple_mixins import ReturningMixin, UpdatesMixin
from flowlab.modules.db.query._where_mixin import WhereMixin

if TYPE_CHECKING:
    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC


class UpdateQuery(SingleQuery, WhereMixin, UpdatesMixin, ReturningMixin):
    def __init__(self, dialect: DialectABC, table: str | list[str], database: DatabaseABC) -> None:
        super().__init__(dialect, table, database)

        self.where: list[Any] = []
        self._updates_dict: dict[str, Any] = {}
        self._returning_list: list[Any] | None = None

    def to_query_with_params(self) -> QueryWithParams:
        return self._dialect.update(
            table=self._table,
            updates=self._updates_dict,
            where=self.where,
            returning=self._returning_list,
        )
