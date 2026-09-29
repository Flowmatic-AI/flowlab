from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query.expressions._sql import SqlABC

if TYPE_CHECKING:
    from flowlab.modules.db.dialects import DialectABC


class Identifier(SqlABC):
    def __init__(self, identifier: str | list[Any]) -> None:
        self._identifier = identifier

    def sql(self, dialect: DialectABC) -> str:
        return dialect.escape_identifier(self._identifier)

    def params(self, dialect: DialectABC) -> list[Any]:
        return []

    def raw_sql(self, dialect: DialectABC) -> str:
        return dialect.escape_identifier(self._identifier)
