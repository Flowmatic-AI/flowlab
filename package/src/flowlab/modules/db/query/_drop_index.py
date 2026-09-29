from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.db.query._ddl_mixins import IfExistsMixin
from flowlab.modules.db.query._query import SingleQuery

if TYPE_CHECKING:
    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC


class DropIndexQuery(SingleQuery, IfExistsMixin):
    def __init__(
        self,
        dialect: DialectABC,
        table: str | list[str],
        database: DatabaseABC,
        name: str,
    ) -> None:
        super().__init__(dialect, table, database)

        self._name: str = name
        self._if_exists: bool = False

    def name(self, name: str) -> Self:
        self._name = name
        return self

    def table(self, table: str | list[str]) -> Self:
        self._table = table
        return self

    def to_query_with_params(self) -> QueryWithParams:
        return self._dialect.drop_index(
            if_exists=self._if_exists,
            name=self._name,
            table=self._table,
        )

    def explain(self, emulate_prepare: bool = False) -> list[dict[str, Any]]:
        return []
