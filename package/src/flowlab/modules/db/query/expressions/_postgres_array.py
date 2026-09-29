from __future__ import annotations

from typing import Any


class PostgresArray:
    """Marks a list as a PostgreSQL array rather than a JSON document.

    A bare ``list`` is serialized to JSON on every dialect, because that is the
    only representation SQLite and MySQL have. PostgreSQL also has a real array
    type, but nothing in the value itself says which of the two is meant, so the
    array reading is opt-in::

        db.insert("rows").values({
            "actual_json_column": [1, 2, 3, 4],
            "postgres_array_column": PostgresArray([5, 6, 7, 8]),
        }).execute()

    Dialects without an array type unwrap it back to JSON, so a query written
    for PostgreSQL still runs against SQLite and MySQL. Reading is unaffected:
    an array column comes back as a plain ``list``.
    """

    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PostgresArray):
            return NotImplemented
        return self.values == other.values

    def __repr__(self) -> str:
        return f"PostgresArray({self.values!r})"
