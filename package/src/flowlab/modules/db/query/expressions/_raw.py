from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query.expressions._sql import SqlABC

if TYPE_CHECKING:
    from flowlab.modules.db.dialects import DialectABC


class Raw(SqlABC):
    def __init__(self, sql: str) -> None:
        self._sql = sql

    def sql(self, dialect: DialectABC) -> str:
        return self._sql

    def params(self, dialect: DialectABC) -> list[Any]:
        return []

    def raw_sql(self, dialect: DialectABC) -> str:
        return self._sql
