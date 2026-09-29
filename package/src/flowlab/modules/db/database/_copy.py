from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flowlab.modules.db._exceptions import DatabaseError

if TYPE_CHECKING:
    from flowlab.modules.db.database._abc import DatabaseABC
    from flowlab.modules.db.query.ddl import TableDescription


def _table_name(description: TableDescription) -> str:
    """Return the bare table name a description refers to, dropping any schema prefix."""
    table = description.table
    if isinstance(table, list):
        return table[-1]
    return table


def _foreign_key_dependencies(description: TableDescription, names_present: set[str]) -> set[str]:
    own_name = _table_name(description)
    dependencies: set[str] = set()

    for foreign_key in description.constraints.foreign_keys:
        ref_table = foreign_key.ref_table
        if ref_table == own_name:
            continue
        if ref_table not in names_present:
            continue
        dependencies.add(ref_table)

    return dependencies


def dependency_order(
    descriptions: list[TableDescription],
) -> tuple[list[TableDescription], list[TableDescription]]:
    """Order descriptions so a table follows every table its foreign keys reference.

    Returns the ordered descriptions together with the subset that could not be
    ordered because they take part in a reference cycle -- those must be created
    without their foreign keys, which are replayed afterwards.
    """
    names_present = {_table_name(description) for description in descriptions}

    ordered: list[TableDescription] = []
    ordered_names: set[str] = set()
    deferred: list[TableDescription] = []

    remaining = list(descriptions)

    while remaining:
        placed_this_pass: list[TableDescription] = []
        still_remaining: list[TableDescription] = []

        for description in remaining:
            dependencies = _foreign_key_dependencies(description, names_present)
            if dependencies.issubset(ordered_names):
                placed_this_pass.append(description)
            else:
                still_remaining.append(description)

        if placed_this_pass:
            for description in placed_this_pass:
                ordered.append(description)
                ordered_names.add(_table_name(description))
            remaining = still_remaining
            continue

        # No progress this pass: a reference cycle runs through every table
        # left. Break it on the first one alone -- created without its foreign
        # keys, which are replayed once every table exists -- and let the next
        # pass place whatever that unblocks with its keys built inline. A table
        # that merely depends on a cycle is not itself part of one, so deferring
        # the whole remainder here would strip keys that can be built normally.
        blocked = still_remaining[0]
        ordered.append(blocked)
        ordered_names.add(_table_name(blocked))
        deferred.append(blocked)

        remaining = still_remaining[1:]

    return ordered, deferred


def copy_database(
    source: DatabaseABC,
    destination: DatabaseABC,
    include_data: bool,
    row_batch_size: int,
) -> int:
    """Copy every table (schema, and optionally data) from source to destination."""
    if row_batch_size < 1:
        raise DatabaseError(f"row_batch_size must be at least 1, got {row_batch_size}")

    descriptions = [source.describe_table(table) for table in source.list_tables()]
    ordered, deferred = dependency_order(descriptions)
    deferred_names = {_table_name(description) for description in deferred}

    total_rows = 0

    for description in ordered:
        is_deferred = _table_name(description) in deferred_names
        description.create_table(destination, skip_foreign_key_constraints=is_deferred)

        if include_data:
            total_rows += _copy_table_data(source, destination, description.table, row_batch_size)

    for description in deferred:
        for foreign_key in description.constraints.foreign_keys:
            destination.alter_table(description.table).add_foreign_key_constraint(
                column=list(foreign_key.columns),
                ref_table=foreign_key.ref_table,
                ref_column=list(foreign_key.ref_columns),
                name=foreign_key.name,
                on_delete=foreign_key.on_delete,
                on_update=foreign_key.on_update,
            ).execute()

    return total_rows


def _copy_table_data(
    source: DatabaseABC,
    destination: DatabaseABC,
    table: str | list[str],
    row_batch_size: int,
) -> int:
    result = source.table(table).select().execute()

    total = 0
    batch: list[dict[str, Any]] = []

    while True:
        row = result.fetch_dict()
        if not row:
            break

        batch.append(row)
        if len(batch) >= row_batch_size:
            destination.insert(table).values(*batch).execute()
            total += len(batch)
            batch = []

    if batch:
        destination.insert(table).values(*batch).execute()
        total += len(batch)

    return total
