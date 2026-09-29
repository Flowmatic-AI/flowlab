from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query.ddl import (
    Column,
    ForeignKeyConstraint,
    Index,
    TableConstraints,
    TableDescription,
    UniqueConstraint,
)
from flowlab.modules.db.query.enums import ReferentialActionEnum

if TYPE_CHECKING:
    from flowlab.modules.db.database._abc import DatabaseABC
    from flowlab.modules.db.dialects import DialectABC


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _referential_action(value: Any) -> ReferentialActionEnum | str | None:
    if value is None:
        return None

    text = str(value).upper()
    for action in ReferentialActionEnum:
        if action.value == text:
            return action

    return str(value)


def parse_columns(dialect: DialectABC, rows: list[dict[str, Any]]) -> list[Column]:
    columns: list[Column] = []

    for row in rows:
        auto_increment = dialect.parse_bool(row["auto_increment"])
        column_type, size = dialect.parse_column_type(str(row["column_type"]), auto_increment)

        default_expression = None if auto_increment else _optional_string(row["default_expression"])
        default = None if default_expression is None else dialect.parse_default(default_expression, column_type)

        columns.append(
            Column(
                name=str(row["column_name"]),
                type=column_type,
                size=size,
                not_null=dialect.parse_bool(row["not_null"]),
                default=default,
                auto_increment=auto_increment,
            )
        )

    return columns


def parse_constraints(rows: list[dict[str, Any]]) -> TableConstraints:
    constraints = TableConstraints()

    unique_by_id: dict[str, UniqueConstraint] = {}
    foreign_keys_by_id: dict[str, ForeignKeyConstraint] = {}

    for row in rows:
        constraint_id = str(row["constraint_id"])
        constraint_type = str(row["constraint_type"])
        name = _optional_string(row["constraint_name"])
        column = str(row["column_name"])

        if constraint_type == "UNIQUE":
            unique = unique_by_id.get(constraint_id)
            if unique is None:
                unique = UniqueConstraint(columns=[], name=name)
                unique_by_id[constraint_id] = unique
                constraints.unique.append(unique)

            unique.columns.append(column)
            continue

        if constraint_type != "FOREIGN KEY":
            continue

        foreign_key = foreign_keys_by_id.get(constraint_id)
        if foreign_key is None:
            foreign_key = ForeignKeyConstraint(
                columns=[],
                ref_table=str(row["ref_table"]),
                ref_columns=[],
                name=name,
                on_delete=_referential_action(row["on_delete"]),
                on_update=_referential_action(row["on_update"]),
            )
            foreign_keys_by_id[constraint_id] = foreign_key
            constraints.foreign_keys.append(foreign_key)

        foreign_key.columns.append(column)
        foreign_key.ref_columns.append(str(row["ref_column"]))

    return constraints


def parse_indexes(dialect: DialectABC, rows: list[dict[str, Any]]) -> list[Index]:
    """Group the index rows into indexes, dropping the ones a CREATE INDEX cannot rebuild."""
    indexes_by_id: dict[str, Index] = {}
    dropped: set[str] = set()

    for row in rows:
        index_id = str(row["index_id"])
        if index_id in dropped:
            continue

        # An expression key reports no column name, and a partial index carries a
        # predicate the builders cannot express: replaying either would build a
        # different index, so neither is described at all.
        if row["column_name"] is None or dialect.parse_bool(row["is_partial"]):
            dropped.add(index_id)
            indexes_by_id.pop(index_id, None)
            continue

        index = indexes_by_id.get(index_id)
        if index is None:
            index = Index(
                name=str(row["index_name"]),
                columns=[],
                unique=dialect.parse_bool(row["is_unique"]),
            )
            indexes_by_id[index_id] = index

        index.columns.append(str(row["column_name"]))

    return list(indexes_by_id.values())


def parse_primary_keys(rows: list[dict[str, Any]]) -> list[str]:
    """Collect the primary key columns, in key order, from the constraint rows."""
    return [str(row["column_name"]) for row in rows if str(row["constraint_type"]) == "PRIMARY KEY"]


def describe_table(database: DatabaseABC, dialect: DialectABC, table: str | list[str]) -> TableDescription:
    column_rows = database.query_with_params(dialect.describe_table_columns(table)).fetch_dicts()
    constraint_rows = database.query_with_params(dialect.describe_table_constraints(table)).fetch_dicts()
    index_rows = database.query_with_params(dialect.describe_table_indexes(table)).fetch_dicts()

    return TableDescription(
        table=table,
        columns=parse_columns(dialect, column_rows),
        primary_keys=parse_primary_keys(constraint_rows),
        constraints=parse_constraints(constraint_rows),
        indexes=parse_indexes(dialect, index_rows),
    )
