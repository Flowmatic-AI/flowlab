from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self, TypeVar

from flowlab.modules.db._threading import ThreadLocalStore
from flowlab.modules.db.result import ResultABC

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound="Model")

if TYPE_CHECKING:
    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.adapters import AdapterABC
    from flowlab.modules.db.database._table import Table
    from flowlab.modules.db.dialects import DialectABC
    from flowlab.modules.db.orm import (
        DeleteModelQuery,
        InsertModelQuery,
        Model,
        SelectModelQuery,
        UpdateModelQuery,
    )
    from flowlab.modules.db.query import (
        AlterTableQuery,
        CreateIndexQuery,
        CreateTableQuery,
        DeleteQuery,
        DropIndexQuery,
        DropTableQuery,
        InsertQuery,
        SelectQuery,
        UpdateQuery,
    )
    from flowlab.modules.db.query.ddl import TableDescription
    from flowlab.modules.db.query.expressions import Alias, SubQuery


class DatabaseABC:
    def __init__(self, adapter: AdapterABC, dialect: DialectABC, ensure_always_connected: bool = False) -> None:
        self._adapter = adapter
        self._dialect = dialect
        self._ensure_always_connected = ensure_always_connected
        self._savepoint_stacks: ThreadLocalStore[list[str]] = ThreadLocalStore()

    @property
    def _savepoints(self) -> list[str]:
        stack = self._savepoint_stacks.current()
        if stack is None:
            stack = []
            self._savepoint_stacks.set(stack)
        return stack

    @property
    def adapter(self) -> AdapterABC:
        return self._adapter

    @property
    def dialect(self) -> DialectABC:
        return self._dialect

    @property
    def ensure_always_connected(self) -> bool:
        return self._ensure_always_connected

    def exec(self, query: str) -> None:
        if self._ensure_always_connected:
            self.reconnect_if_disconnected()

        return self._adapter.exec(query)

    def query(self, query: str) -> ResultABC:
        if self._ensure_always_connected:
            self.reconnect_if_disconnected()

        return self._adapter.query(query)

    def prepared(self, query: str, params: list[Any] | None = None, emulate: bool = False) -> ResultABC:
        from flowlab.modules.db._query_with_params import QueryWithParams

        qwp = QueryWithParams(query=query, params=params or [])
        return self.query_with_params(qwp, emulate)

    def query_with_params(self, qwp: QueryWithParams, emulate: bool = False) -> ResultABC:
        if self._ensure_always_connected:
            self.reconnect_if_disconnected()

        if len(qwp.params) > 0:
            return self._adapter.query_with_params(self._dialect, qwp, emulate)
        return self._adapter.query(qwp.query)

    def begin_transaction(self, name: str | None = None) -> None:
        if not self.in_transaction:
            qwp = self._dialect.begin_transaction(name)
            self._adapter.begin_transaction(qwp.query)
            return

        name = name or f"savepoint_{len(self._savepoints) + 1}"
        self._savepoints.append(name)
        qwp = self._dialect.begin_savepoint(name)
        self._adapter.begin_savepoint(qwp.query)

    def commit_transaction(self, release_savepoints: bool = False, name: str | None = None) -> None:
        if not self.in_transaction:
            return

        if release_savepoints or len(self._savepoints) == 0:
            self._savepoints.clear()
            qwp = self._dialect.commit_transaction(name)
            self._adapter.commit_transaction(qwp.query)
            return

        qwp = self._dialect.commit_savepoint(self._savepoints.pop())
        self._adapter.commit_savepoint(qwp.query)

    def rollback_transaction(self, release_savepoints: bool = False, name: str | None = None) -> None:
        if not self.in_transaction:
            return

        if release_savepoints or len(self._savepoints) == 0:
            self._savepoints.clear()
            qwp = self._dialect.rollback_transaction(name)
            self._adapter.rollback_transaction(qwp.query)
            return

        qwp = self._dialect.rollback_savepoint(self._savepoints.pop())
        self._adapter.rollback_savepoint(qwp.query)

    @property
    def in_transaction(self) -> bool:
        return self._adapter.in_transaction

    def transaction(
        self, callback: Callable[[Self], T], release_savepoints: bool = False, name: str | None = None
    ) -> T:
        self.begin_transaction(name=name)
        try:
            result = callback(self)
            self.commit_transaction(release_savepoints=release_savepoints, name=name)
            return result
        except Exception:
            self.rollback_transaction(release_savepoints=release_savepoints, name=name)
            raise

    def last_insert_id(self, name: str | None = None) -> int | str | None:
        return self._adapter.last_insert_id(name)

    def select(self, table: str | list[str] | Alias | SubQuery) -> SelectQuery:
        from flowlab.modules.db.query import SelectQuery

        return SelectQuery(self._dialect, table, database=self)

    def select_table(self, table: str | list[str], alias: str | None = None) -> SelectQuery:
        if alias:
            from flowlab.modules.db.query.expressions import Alias

            return self.select(Alias(table, alias))

        return self.select(table)

    def select_sub_query(self, sub_query: Any, alias: str) -> SelectQuery:
        from flowlab.modules.db.query.expressions import SubQuery

        return self.select(SubQuery(sub_query, alias))

    def select_models(self, model: type[ModelT]) -> SelectModelQuery[ModelT]:
        from flowlab.modules.db.orm import SelectModelQuery

        return SelectModelQuery(self._dialect, self, model)

    def insert_models(self, models: list[ModelT]) -> InsertModelQuery[ModelT]:
        from flowlab.modules.db.orm import InsertModelQuery

        return InsertModelQuery(self._dialect, self, models)

    def insert_model(self, model: ModelT) -> InsertModelQuery[ModelT]:
        return self.insert_models([model])

    def update_models(self, models: list[ModelT]) -> UpdateModelQuery[ModelT]:
        from flowlab.modules.db.orm import UpdateModelQuery

        return UpdateModelQuery(self._dialect, self, models)

    def update_model(self, model: ModelT) -> UpdateModelQuery[ModelT]:
        return self.update_models([model])

    def delete_models(self, models: list[ModelT]) -> DeleteModelQuery[ModelT]:
        from flowlab.modules.db.orm import DeleteModelQuery

        return DeleteModelQuery(self._dialect, self, models)

    def delete_model(self, model: ModelT) -> DeleteModelQuery[ModelT]:
        return self.delete_models([model])

    def insert(self, table: str | list[str]) -> InsertQuery:
        from flowlab.modules.db.query import InsertQuery

        return InsertQuery(self._dialect, table, database=self)

    def update(self, table: str | list[str]) -> UpdateQuery:
        from flowlab.modules.db.query import UpdateQuery

        return UpdateQuery(self._dialect, table, database=self)

    def delete(self, table: str | list[str]) -> DeleteQuery:
        from flowlab.modules.db.query import DeleteQuery

        return DeleteQuery(self._dialect, table, database=self)

    def create_table(self, table: str | list[str]) -> CreateTableQuery:
        from flowlab.modules.db.query import CreateTableQuery

        return CreateTableQuery(self._dialect, table, database=self)

    def alter_table(self, table: str | list[str]) -> AlterTableQuery:
        from flowlab.modules.db.query import AlterTableQuery

        return AlterTableQuery(self._dialect, table, database=self)

    def drop_table(self, table: str | list[str]) -> DropTableQuery:
        from flowlab.modules.db.query import DropTableQuery

        return DropTableQuery(self._dialect, table, database=self)

    def create_index(self, table: str | list[str], name: str) -> CreateIndexQuery:
        from flowlab.modules.db.query import CreateIndexQuery

        return CreateIndexQuery(self._dialect, table, database=self, name=name)

    def drop_index(self, table: str | list[str], name: str) -> DropIndexQuery:
        from flowlab.modules.db.query import DropIndexQuery

        return DropIndexQuery(self._dialect, table, database=self, name=name)

    def list_tables(self, schema: str = "public") -> list[str]:
        return self.query_with_params(self._dialect.list_tables(schema)).scalars()

    def describe_table(self, table: str | list[str]) -> TableDescription:
        from flowlab.modules.db.database._introspection import describe_table

        return describe_table(self, self._dialect, table)

    def table(self, table: str | list[str]) -> Table:
        from flowlab.modules.db.database._table import Table

        return Table(self, self._dialect, table)

    def copy_from(self, source: DatabaseABC, include_data: bool = True, row_batch_size: int = 100) -> int:
        """Copy every table from source into this database."""
        from flowlab.modules.db.database._copy import copy_database

        return copy_database(source, self, include_data, row_batch_size)

    def copy_to(self, destination: DatabaseABC, include_data: bool = True, row_batch_size: int = 100) -> int:
        """Copy every table from this database into destination."""
        from flowlab.modules.db.database._copy import copy_database

        return copy_database(self, destination, include_data, row_batch_size)

    def close(self) -> None:
        self.adapter.close()

    def is_connected(self) -> bool:
        return self.adapter.is_connected()

    def reconnect(self) -> None:
        self._savepoints.clear()
        self.adapter.reconnect()

    def reconnect_if_disconnected(self) -> bool:
        if self.adapter.is_connected():
            return False

        self.reconnect()
        return True

    def get_connection(self) -> Any:
        return self.adapter.get_connection()
