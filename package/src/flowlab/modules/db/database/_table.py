from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from flowlab.modules.db import QueryError
from flowlab.modules.db.result import Result, ResultABC

if TYPE_CHECKING:
    from flowlab.modules.db.database._abc import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC
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
        WhereGroup,
    )
    from flowlab.modules.db.query.ddl import TableDescription


def _single_result(result: ResultABC | list[ResultABC]) -> ResultABC:
    if not isinstance(result, list):
        return result

    if len(result) != 1:
        raise QueryError(f"Expected a single ResultABC for a single-row insert, got {len(result)}")

    return result[0]


class Table:
    def __init__(self, database: DatabaseABC, dialect: DialectABC, table: str | list[str]) -> None:
        self._database = database
        self._dialect = dialect
        self._table = table

    def select(self, columns: list[Any] | None = None) -> SelectQuery:
        q = self._database.select(self._table)
        if columns:
            q.columns(columns)
        return q

    def insert(self, *values: dict[str, Any]) -> InsertQuery:
        return self._database.insert(self._table).values(*values)

    @staticmethod
    def _matching_group(columns: list[str], values: dict[str, Any]) -> Callable[[WhereGroup], WhereGroup]:
        def build(group: WhereGroup) -> WhereGroup:
            for column in columns:
                group.where_equals(column, values[column])
            return group

        return build

    def select_or_insert(
        self,
        columns: list[str],
        values: dict[str, Any],
        last_insert_id: str | None = None,
        emulate_prepare: bool = False,
    ) -> ResultABC:
        result = self.select().where_group(self._matching_group(columns, values)).execute(emulate_prepare)

        rows = result.fetch_dicts()
        if len(rows) > 0:
            return Result(result.columns(), rows)

        insert_query = self.insert(values).returning([])
        if last_insert_id:
            insert_query.last_insert_id(last_insert_id)

        return _single_result(insert_query.execute(emulate_prepare))

    def insert_or_ignore(
        self,
        columns: list[str],
        values: dict[str, Any],
        last_insert_id: str | None = None,
        emulate_prepare: bool = False,
    ) -> ResultABC:
        insert_query = self.insert(values).on_conflict_do_nothing(columns)
        if last_insert_id:
            insert_query.last_insert_id(last_insert_id)

        return _single_result(insert_query.execute(emulate_prepare))

    def insert_or_update(
        self,
        columns: list[str],
        values: dict[str, Any],
        last_insert_id: str | None = None,
        emulate_prepare: bool = False,
    ) -> ResultABC:
        insert_query = self.insert(values).on_conflict_do_update(columns)
        if last_insert_id:
            insert_query.last_insert_id(last_insert_id)

        return _single_result(insert_query.execute(emulate_prepare))

    def update(self, values: dict[str, Any]) -> UpdateQuery:
        return self._database.update(self._table).updates(values)

    def delete(self) -> DeleteQuery:
        return self._database.delete(self._table)

    def create(self, callback: Callable[..., Any] | None = None) -> CreateTableQuery:
        query = self._database.create_table(self._table)
        if callback:
            callback(query)
        return query

    def create_if_not_exists(self, callback: Callable[..., Any] | None = None) -> CreateTableQuery:
        return self.create(callback).if_not_exists()

    def alter(self, callback: Callable[..., Any] | None = None) -> AlterTableQuery:
        query = self._database.alter_table(self._table)
        if callback:
            callback(query)
        return query

    def truncate(self) -> None:
        self.delete().execute()

    def drop(self) -> DropTableQuery:
        return self._database.drop_table(self._table)

    def drop_if_exists(self) -> DropTableQuery:
        return self.drop().if_exists()

    def create_index(self, name: str, columns: str | list[Any]) -> CreateIndexQuery:
        return self._database.create_index(self._table, name).columns(columns)

    def drop_index(self, name: str) -> DropIndexQuery:
        return self._database.drop_index(self._table, name)

    def describe(self) -> TableDescription:
        return self._database.describe_table(self._table)

    def columns(self) -> list[str]:
        columns = self.select().limit(0).execute().columns()
        return list(columns.keys()) if isinstance(columns, dict) else list(columns)

    def is_empty(self) -> bool:
        return self.select().limit(1).count() == 0

    def copy_from(
        self,
        from_: str | list[str] | Table,
        map: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        ignore_exceptions: bool = False,
        emulate_prepare: bool = False,
    ) -> int:
        table = from_ if isinstance(from_, Table) else self._database.table(from_)
        columns = table.columns()

        result = table.select().execute(emulate_prepare)

        count = 0
        while True:
            assoc = result.fetch_dict()
            if not assoc:
                break

            try:
                row = map(assoc) if map else assoc
                filtered = {column: value for column, value in row.items() if column in columns}
                self.insert(filtered).execute(emulate_prepare)
                count += 1
            except Exception:
                if ignore_exceptions:
                    continue
                raise

        return count

    def copy_to(
        self,
        to: str | list[str] | Table,
        map: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        ignore_exceptions: bool = False,
        emulate_prepare: bool = False,
    ) -> int:
        table = to if isinstance(to, Table) else self._database.table(to)
        columns = table.columns()

        result = self.select().execute()

        count = 0
        while True:
            assoc = result.fetch_dict()
            if not assoc:
                break

            try:
                row = map(assoc) if map else assoc
                filtered = {column: value for column, value in row.items() if column in columns}
                table.insert(filtered).execute(emulate_prepare)
                count += 1
            except Exception:
                if ignore_exceptions:
                    continue
                raise

        return count
