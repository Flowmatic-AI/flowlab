from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from flowlab.modules.db.query.ddl._column import Column
from flowlab.modules.db.query.ddl._foreign_key_constraint import ForeignKeyConstraint
from flowlab.modules.db.query.ddl._index import Index
from flowlab.modules.db.query.ddl._unique_constraint import UniqueConstraint

if TYPE_CHECKING:
    from flowlab.modules.db.database import DatabaseABC
    from flowlab.modules.db.result import ResultABC


@dataclass
class TableConstraints:
    unique: list[UniqueConstraint] = field(default_factory=list)
    foreign_keys: list[ForeignKeyConstraint] = field(default_factory=list)


@dataclass
class TableDescription:
    table: str | list[str] = ""
    columns: list[Column] = field(default_factory=list)
    primary_keys: list[str] = field(default_factory=list)
    constraints: TableConstraints = field(default_factory=TableConstraints)
    indexes: list[Index] = field(default_factory=list)

    def create_table(
        self,
        db: DatabaseABC,
        if_not_exists: bool = False,
        override_name: str | None = None,
        skip_unique_constraints: bool = False,
        skip_foreign_key_constraints: bool = False,
        skip_indexes: bool = False,
    ) -> ResultABC:
        """Recreate the described table on ``db`` and run the statement."""
        table_name = override_name if override_name is not None else self.table

        query = db.create_table(table_name)

        if if_not_exists:
            query.if_not_exists()

        for column in self.columns:
            query.column(
                name=column.name,
                type_=column.type,
                not_null=column.not_null,
                default=column.default,
                generated_by_default_as_identity=column.auto_increment,
                size=column.size,
            )

        if self.primary_keys:
            query.primary_keys(list(self.primary_keys))

        if not skip_unique_constraints:
            for unique in self.constraints.unique:
                query.unique_constraint(list(unique.columns), unique.name)

        if not skip_foreign_key_constraints:
            for foreign_key in self.constraints.foreign_keys:
                query.foreign_key_constraint(
                    column=list(foreign_key.columns),
                    ref_table=foreign_key.ref_table,
                    ref_column=list(foreign_key.ref_columns),
                    name=foreign_key.name,
                    on_delete=foreign_key.on_delete,
                    on_update=foreign_key.on_update,
                )

        result = query.execute()

        # An index is a statement of its own, so it can only be built once the table is.
        if not skip_indexes:
            for index in self.indexes:
                index_query = db.create_index(table_name, index.name).columns(list(index.columns))

                if index.unique:
                    index_query.unique()

                # MySQL has no CREATE INDEX IF NOT EXISTS, and asking for one there raises.
                if if_not_exists and db.dialect.index_if_not_exists:
                    index_query.if_not_exists()

                index_query.execute()

        return result
