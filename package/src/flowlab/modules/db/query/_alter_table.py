from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query._ddl_mixins import AltersMixin
from flowlab.modules.db.query._query import MultiQuery
from flowlab.modules.db.query.ddl import AlterABC

if TYPE_CHECKING:
    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC


class AlterTableQuery(MultiQuery, AltersMixin):
    def __init__(self, dialect: DialectABC, table: str | list[str], database: DatabaseABC) -> None:
        super().__init__(dialect, table, database)

        self._alters: list[AlterABC] = []

    def to_query_with_params(self) -> list[QueryWithParams]:
        return self._dialect.alter_table(
            table=self._table,
            alters=self._alters,
        )

    def explain(self, emulate_prepare: bool = False) -> list[dict[str, Any]]:
        return []
