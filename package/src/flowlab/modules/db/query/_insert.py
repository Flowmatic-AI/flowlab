from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.db import QueryError
from flowlab.modules.db._query_with_params import QueryWithParams
from flowlab.modules.db.query._query import Query
from flowlab.modules.db.query._simple_mixins import LastInsertIdMixin, OnConflictMixin, ReturningMixin, ValuesMixin
from flowlab.modules.db.result import Result, ResultABC

if TYPE_CHECKING:
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC
    from flowlab.modules.db.query._on_conflict import OnConflict
    from flowlab.modules.db.query._where_mixin import WhereGroup


class InsertQuery(Query, ValuesMixin, OnConflictMixin, ReturningMixin, LastInsertIdMixin):
    def __init__(self, dialect: DialectABC, table: str | list[str], database: DatabaseABC) -> None:
        super().__init__(dialect, table, database)

        self._table: str | list[str] = table

        self._values_list: list[dict[str, Any]] = []
        self._on_conflict: OnConflict | None = None
        self._returning_list: list[Any] | None = None
        self._last_insert_id_col: str | None = None

        self._emulate_on_conflict = False
        self._emulate_on_conflict_in_transaction = False
        self._emulate_returning = False

    @property
    def _emulating_on_conflict(self) -> bool:
        """ON CONFLICT is emulated whenever the dialect cannot express it, and
        on request even when it can."""
        if self._on_conflict is None:
            return False

        return self._emulate_on_conflict or not self._dialect.on_conflict

    @property
    def _emulating_returning(self) -> bool:
        """RETURNING is emulated whenever the dialect cannot express it, and on
        request even when it can."""
        if self._returning_list is None:
            return False

        return self._emulate_returning or not self._dialect.returning

    def to_query_with_params(self) -> QueryWithParams:
        return self._dialect.insert(
            table=self._table,
            values=self._values_list,
            on_conflict=None if self._emulating_on_conflict else self._on_conflict,
            returning=None if self._emulating_returning else self._returning_list,
            last_insert_id=self._last_insert_id_col,
        )

    def to_sql(self) -> str:
        return self.to_query_with_params().to_sql(self._dialect)

    def explain(self, emulate_prepare: bool = False) -> list[dict[str, Any]]:
        return self._explain(self.to_query_with_params(), emulate_prepare)

    def execute(self, emulate_prepare: bool = False) -> ResultABC | list[ResultABC]:
        if self._emulating_returning and not self._last_insert_id_col:
            raise QueryError(
                "RETURNING has to be emulated on this dialect, which needs the primary key "
                'column to read the inserted row back: chain .last_insert_id("id") '
                "onto the insert"
            )

        if not self._emulating_on_conflict:
            if self._emulating_returning:
                return self._insert(self._values_list, self._on_conflict, emulate_prepare)

            return self._run(self.to_query_with_params(), emulate_prepare)

        def _callback(_database: DatabaseABC) -> ResultABC | list[ResultABC]:
            results = [self._upsert(values, emulate_prepare) for values in self._values_list]

            return results[0] if len(results) == 1 else results

        if self._emulate_on_conflict_in_transaction:
            return self._database.transaction(_callback)

        return _callback(self._database)

    def _upsert(self, values: dict[str, Any], emulate_prepare: bool) -> ResultABC:
        assert self._on_conflict is not None

        if isinstance(self._on_conflict.conflict, str):
            raise QueryError("database does not support named constraints")

        conflict: dict[str, Any] = {}

        for column in self._on_conflict.conflict:
            if column not in values:
                raise QueryError("insert values does not contain constraint columns")

            conflict[column] = values[column]

        def _where_group(condition_group: WhereGroup) -> None:
            for column, value in conflict.items():
                condition_group.where_equals(column, value)

        result = self._select(_where_group, 2, emulate_prepare)

        rows = result.fetch_dicts()
        count = len(rows)

        if count == 0:
            return self._insert([values], None, emulate_prepare)

        if count > 1:
            raise QueryError("multiple rows in constraint")

        return (
            self._update(values, conflict, emulate_prepare)
            if self._on_conflict.updates is not None
            else self._ignore(result, rows)
        )

    def _select(self, where_group: Callable[[WhereGroup], Any], limit: int, emulate_prepare: bool) -> ResultABC:
        columns: list[Any] = []

        if self._returning_list:
            seen: set[Any] = set()

            for column in [self._last_insert_id_col, *self._returning_list]:
                if not column or column in seen:
                    continue

                seen.add(column)
                columns.append(column)

        select_query = self._database.select(self._table).columns(columns).where_group(where_group).limit(limit)

        if self._last_insert_id_col:
            select_query.order_by_desc(self._last_insert_id_col)

        return select_query.execute(emulate_prepare)

    def _insert(
        self,
        values: list[dict[str, Any]],
        on_conflict: OnConflict | None,
        emulate_prepare: bool,
    ) -> ResultABC:
        result = self._database.query_with_params(
            self._dialect.insert(
                table=self._table,
                values=values,
                on_conflict=on_conflict,
                returning=None if self._emulating_returning else self._returning_list,
                last_insert_id=self._last_insert_id_col,
            )
        )

        if not self._emulating_returning or not self._last_insert_id_col:
            return result

        last_insert_id_col = self._last_insert_id_col
        last_insert_id = self._database.last_insert_id()

        def _where_group(condition_group: WhereGroup) -> WhereGroup:
            if not last_insert_id:
                return condition_group

            return condition_group.where_equals(last_insert_id_col, last_insert_id)

        return self._select(_where_group, 1, emulate_prepare)

    def _update(self, values: dict[str, Any], conflict: dict[str, Any], emulate_prepare: bool) -> ResultABC:
        assert self._on_conflict is not None

        update_query = self._database.update(self._table)

        updates = (
            (self._on_conflict.updates if len(self._on_conflict.updates) > 0 else values)
            if self._on_conflict.updates is not None
            else conflict
        )

        update_query.updates(updates)

        for column, value in conflict.items():
            update_query.where_equals(column, value)

        if self._returning_list is not None:
            update_query.returning(self._returning_list)

        result = update_query.execute(emulate_prepare)

        if not self._emulating_returning:
            return result

        def _where_group(condition_group: WhereGroup) -> None:
            for column, value in conflict.items():
                condition_group.where_equals(column, value)

        return self._select(_where_group, 1, emulate_prepare)

    def _ignore(self, result: ResultABC, rows: list[dict[str, Any]]) -> ResultABC:
        returning = self._returning_list is not None

        return Result(
            columns=result.columns() if returning else {},
            rows=rows if returning else [],
        )

    def into(self, table: str | list[str]) -> Self:
        self._table = table

        return self

    def emulate_on_conflict(self, last_insert_id: str, in_transaction: bool = False) -> Self:
        """Force the select-then-insert-or-update emulation even on a dialect
        with native ON CONFLICT. Dialects without one emulate by themselves."""
        self._emulate_on_conflict = True
        self._emulate_on_conflict_in_transaction = in_transaction
        self._last_insert_id_col = last_insert_id

        return self

    def emulate_returning(self, last_insert_id: str) -> Self:
        """Force the insert-then-select emulation even on a dialect with native
        RETURNING. Dialects without one emulate by themselves, given the primary
        key column -- from here or from ``last_insert_id()``."""
        self._emulate_returning = True
        self._last_insert_id_col = last_insert_id

        return self
