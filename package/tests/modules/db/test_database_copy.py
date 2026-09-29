from __future__ import annotations

import pytest

from flowlab.modules.db import DB
from flowlab.modules.db._exceptions import DatabaseError
from flowlab.modules.db.database._copy import dependency_order
from flowlab.modules.db.query.ddl import Column, ForeignKeyConstraint, TableConstraints, TableDescription
from flowlab.modules.db.query.enums import TypeEnum


def _fresh_db() -> DB:
    return DB.connect_sqlite(":memory:")


def _create_authors_and_books(db: DB) -> None:
    """Create `books` before `authors` on purpose, so a naive list-order or
    alphabetical replay would try to add the foreign key before its target
    table exists."""
    db.create_table("books").if_not_exists().identity("id").string("title").integer(
        "author_id", not_null=False
    ).foreign_key_constraint(column="author_id", ref_table="authors", ref_column="id").execute()

    db.create_table("authors").if_not_exists().identity("id").string("name").execute()

    db.insert("authors").values({"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}).execute()
    db.insert("books").values(
        {"id": 1, "title": "Book A", "author_id": 1},
        {"id": 2, "title": "Book B", "author_id": 2},
    ).execute()


def _employee_description() -> TableDescription:
    return TableDescription(
        table="employees",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True),
            Column(name="manager_id", type=TypeEnum.INT),
        ],
        primary_keys=["id"],
        constraints=TableConstraints(
            foreign_keys=[
                ForeignKeyConstraint(columns=["manager_id"], ref_table="employees", ref_columns=["id"]),
            ],
        ),
    )


def _cycle_descriptions() -> list[TableDescription]:
    a = TableDescription(
        table="a",
        columns=[Column(name="id", type=TypeEnum.INT), Column(name="b_id", type=TypeEnum.INT)],
        primary_keys=["id"],
        constraints=TableConstraints(
            foreign_keys=[ForeignKeyConstraint(columns=["b_id"], ref_table="b", ref_columns=["id"])],
        ),
    )
    b = TableDescription(
        table="b",
        columns=[Column(name="id", type=TypeEnum.INT), Column(name="a_id", type=TypeEnum.INT)],
        primary_keys=["id"],
        constraints=TableConstraints(
            foreign_keys=[ForeignKeyConstraint(columns=["a_id"], ref_table="a", ref_columns=["id"])],
        ),
    )
    return [a, b]


def test_copy_orders_tables_by_dependency_not_input_order() -> None:
    source = _fresh_db()
    _create_authors_and_books(source)

    destination = _fresh_db()
    rows_copied = destination.copy_from(source)

    tables = set(destination.list_tables(schema="main"))
    assert {"authors", "books"} <= tables

    books_description = destination.describe_table("books")
    foreign_keys = books_description.constraints.foreign_keys
    assert len(foreign_keys) == 1
    assert foreign_keys[0].ref_table == "authors"

    assert rows_copied == 4


def test_copy_data_in_batches_smaller_than_table() -> None:
    source = _fresh_db()
    source.create_table("items").if_not_exists().identity("id").string("name").execute()
    source.insert("items").values(*[{"name": f"item-{i}"} for i in range(7)]).execute()

    destination = _fresh_db()
    rows_copied = destination.copy_from(source, row_batch_size=3)

    assert rows_copied == 7
    rows = destination.select("items").execute().fetch_dicts()
    assert {row["name"] for row in rows} == {f"item-{i}" for i in range(7)}


def test_copy_without_data_creates_tables_but_no_rows() -> None:
    source = _fresh_db()
    source.create_table("items").if_not_exists().identity("id").string("name").execute()
    source.insert("items").values({"name": "a"}, {"name": "b"}).execute()

    destination = _fresh_db()
    rows_copied = destination.copy_from(source, include_data=False)

    assert rows_copied == 0
    assert "items" in destination.list_tables(schema="main")
    assert destination.select("items").execute().fetch_dicts() == []


def test_copy_to_and_copy_from_are_mirror_images() -> None:
    source = _fresh_db()
    _create_authors_and_books(source)

    via_copy_from = _fresh_db()
    rows_via_copy_from = via_copy_from.copy_from(source)

    via_copy_to = _fresh_db()
    rows_via_copy_to = source.copy_to(via_copy_to)

    assert rows_via_copy_from == rows_via_copy_to

    for db in (via_copy_from, via_copy_to):
        assert set(db.list_tables(schema="main")) >= {"authors", "books"}
        assert len(db.select("authors").execute().fetch_dicts()) == 2
        assert len(db.select("books").execute().fetch_dicts()) == 2


def test_copy_rejects_row_batch_size_below_one() -> None:
    source = _fresh_db()
    source.create_table("items").if_not_exists().identity("id").string("name").execute()

    destination = _fresh_db()

    with pytest.raises(DatabaseError):
        destination.copy_from(source, row_batch_size=0)


def test_dependency_order_keeps_self_reference_undeferred() -> None:
    ordered, deferred = dependency_order([_employee_description()])

    assert [description.table for description in ordered] == ["employees"]
    assert deferred == []


def test_dependency_order_breaks_a_reference_cycle_on_one_table_only() -> None:
    """A two-table cycle only needs ONE of the pair stripped of its foreign
    keys: once `a` exists, `b` can be built with its key to `a` inline, and
    only `a`'s key waits for the replay."""
    ordered, deferred = dependency_order(_cycle_descriptions())

    assert [description.table for description in ordered] == ["a", "b"]
    assert [description.table for description in deferred] == ["a"]


def test_dependency_order_does_not_defer_a_table_that_merely_follows_a_cycle() -> None:
    """`c` references the cycle but is in no cycle itself, so it is orderable:
    deferring it would strip a foreign key that builds inline -- and on SQLite,
    which cannot add one to an existing table, would fail the copy outright."""
    a, b = _cycle_descriptions()
    c = TableDescription(
        table="c",
        columns=[Column(name="id", type=TypeEnum.INT), Column(name="a_id", type=TypeEnum.INT)],
        primary_keys=["id"],
        constraints=TableConstraints(
            foreign_keys=[ForeignKeyConstraint(columns=["a_id"], ref_table="a", ref_columns=["id"])],
        ),
    )

    ordered, deferred = dependency_order([a, b, c])

    assert [description.table for description in deferred] == ["a"]
    assert [description.table for description in ordered] == ["a", "b", "c"]


def test_dependency_order_ignores_a_reference_to_a_table_outside_the_copy() -> None:
    """A key pointing at a table that is not part of the copy is not an edge --
    it may live in another schema -- so it neither orders nor defers anything."""
    orphan = TableDescription(
        table="orphan",
        columns=[Column(name="id", type=TypeEnum.INT), Column(name="elsewhere_id", type=TypeEnum.INT)],
        primary_keys=["id"],
        constraints=TableConstraints(
            foreign_keys=[
                ForeignKeyConstraint(columns=["elsewhere_id"], ref_table="elsewhere", ref_columns=["id"]),
            ],
        ),
    )

    ordered, deferred = dependency_order([orphan])

    assert [description.table for description in ordered] == ["orphan"]
    assert deferred == []
