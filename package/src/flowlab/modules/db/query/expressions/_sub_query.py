from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query.expressions._sql import SqlABC

if TYPE_CHECKING:
    from flowlab.modules.db.dialects import DialectABC
    from flowlab.modules.db.query import SelectQuery


class SubQuery(SqlABC):
    def __init__(self, query: SelectQuery, alias: str) -> None:
        self._query = query
        self._alias = alias

    def sql(self, dialect: DialectABC) -> str:
        qwp = self._query.to_query_with_params()
        return f"({qwp.query}) AS {dialect.escape_identifier(self._alias)}"

    def params(self, dialect: DialectABC) -> list[Any]:
        return self._query.to_query_with_params().params

    def raw_sql(self, dialect: DialectABC) -> str:
        qwp = self._query.to_query_with_params()
        return f"({qwp.to_sql(dialect)}) AS {dialect.escape_identifier(self._alias)}"
