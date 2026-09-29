"""Booleans have to survive the round trip on the dialects that have no
boolean type of their own.

PostgreSQL stores a real BOOLEAN and its drivers hand one back, so there is
nothing to do there. SQLite stores 0/1 under a declared BOOLEAN column and MySQL
stores a TINYINT; both are decoded back to ``bool`` by their result layer.
"""

from __future__ import annotations

from typing import Any

from flowlab.modules.db.database import DB
from flowlab.modules.db.result import MySQLResult

_MYSQL_TINYINT = 1
_MYSQL_BIGINT = 8


class _FakeCursor:
    """Stands in for a mysql.connector cursor: description tuples carry the
    column name and the wire type code."""

    def __init__(self, description: list[tuple[str, int]], rows: list[tuple[Any, ...]]) -> None:
        self.description = description
        self._rows = list(rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows.pop(0) if self._rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows = list(self._rows)
        self._rows.clear()
        return rows


def test_sqlite_booleans_round_trip() -> None:
    db = DB.connect_sqlite(":memory:")
    db.create_table("flags").if_not_exists().identity("id").boolean("active").execute()
    db.insert("flags").values({"active": True}, {"active": False}).execute()

    rows = db.select("flags").order_by_asc("id").execute().fetch_dicts()

    assert rows[0]["active"] is True
    assert rows[1]["active"] is False


def test_sqlite_boolean_default_round_trips() -> None:
    db = DB.connect_sqlite(":memory:")
    db.create_table("flags").if_not_exists().identity("id").boolean("active", default=True).execute()
    db.insert("flags").values({"id": 1}).execute()

    assert db.select("flags").execute().scalar("active") is True


def test_sqlite_null_boolean_stays_none() -> None:
    db = DB.connect_sqlite(":memory:")
    db.create_table("flags").if_not_exists().identity("id").boolean("active").execute()
    db.insert("flags").values({"active": None}).execute()

    assert db.select("flags").execute().scalar("active") is None


def test_mysql_tinyint_columns_decode_as_booleans() -> None:
    result = MySQLResult(
        _FakeCursor(
            [("id", _MYSQL_BIGINT), ("active", _MYSQL_TINYINT)],
            [(1, 1), (2, 0), (3, None)],
        )
    )

    rows = result.fetch_dicts()

    assert rows[0] == {"id": 1, "active": True}
    assert rows[1] == {"id": 2, "active": False}
    assert rows[2] == {"id": 3, "active": None}
