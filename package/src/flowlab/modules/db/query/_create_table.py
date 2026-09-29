from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query._ddl_mixins import (
    ColumnsDefinitionMixin,
    ConstraintsMixin,
    IfNotExistsMixin,
    PrimaryKeysMixin,
)
from flowlab.modules.db.query._query import SingleQuery
from flowlab.modules.db.query.ddl import Column, ConstraintABC

if TYPE_CHECKING:
    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC


class CreateTableQuery(SingleQuery, ColumnsDefinitionMixin, PrimaryKeysMixin, ConstraintsMixin, IfNotExistsMixin):
    def __init__(self, dialect: DialectABC, table: str | list[str], database: DatabaseABC) -> None:
        super().__init__(dialect, table, database)

        self._columns: list[Column] = []
        self._primary_keys: list[str] = []
        self._constraints: list[ConstraintABC] = []
        self._if_not_exists: bool = False

    def to_query_with_params(self) -> QueryWithParams:
        return self._dialect.create_table(
            if_not_exists=self._if_not_exists,
            table=self._table,
            columns=self._columns,
            primary_keys=self._primary_keys if self._primary_keys else None,
            constraints=self._constraints if self._constraints else None,
        )

    def explain(self, emulate_prepare: bool = False) -> list[dict[str, Any]]:
        return []
