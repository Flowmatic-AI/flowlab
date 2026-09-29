from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from flowlab.modules.db._query_with_params import QueryWithParams
from flowlab.modules.db.result import ResultABC

if TYPE_CHECKING:
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC
    from flowlab.modules.db.query.expressions import Alias, SubQuery


class Query(ABC):
    def __init__(self, dialect: DialectABC, table: str | list[str] | Alias | SubQuery, database: DatabaseABC) -> None:
        super().__init__()

        self._dialect = dialect
        self._table = table
        self._database = database

    @property
    def dialect(self) -> DialectABC:
        return self._dialect

    @abstractmethod
    def to_query_with_params(self) -> QueryWithParams | list[QueryWithParams]: ...

    @abstractmethod
    def to_sql(self) -> str | list[str]: ...

    @abstractmethod
    def execute(self, emulate_prepare: bool = False) -> ResultABC | list[ResultABC]: ...

    @abstractmethod
    def explain(self, emulate_prepare: bool = False) -> list[dict[str, Any]]: ...

    def _explain(self, qwp: QueryWithParams, emulate_prepare: bool) -> list[dict[str, Any]]:
        explain_qwp = QueryWithParams(query=f"EXPLAIN {qwp.query}", params=qwp.params)
        return self._database.query_with_params(explain_qwp, emulate_prepare).fetch_dicts()

    def _run(self, qwp: QueryWithParams, emulate_prepare: bool) -> ResultABC:
        return self._database.query_with_params(qwp, emulate_prepare)


class SingleQuery(Query):
    @abstractmethod
    def to_query_with_params(self) -> QueryWithParams: ...

    def to_sql(self) -> str:
        return self.to_query_with_params().to_sql(self._dialect)

    def execute(self, emulate_prepare: bool = False) -> ResultABC:
        return self._run(self.to_query_with_params(), emulate_prepare)

    def explain(self, emulate_prepare: bool = False) -> list[dict[str, Any]]:
        return self._explain(self.to_query_with_params(), emulate_prepare)


class MultiQuery(Query):
    @abstractmethod
    def to_query_with_params(self) -> list[QueryWithParams]: ...

    def to_sql(self) -> list[str]:
        return [qwp.to_sql(self._dialect) for qwp in self.to_query_with_params()]

    def execute(self, emulate_prepare: bool = False) -> list[ResultABC]:
        return [self._run(qwp, emulate_prepare) for qwp in self.to_query_with_params()]

    def explain(self, emulate_prepare: bool = False) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for qwp in self.to_query_with_params():
            results.extend(self._explain(qwp, emulate_prepare))

        return results
