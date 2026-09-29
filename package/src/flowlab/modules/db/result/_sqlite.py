from __future__ import annotations

from datetime import date, datetime
from typing import Any

from flowlab.modules.db.result._base import ResultABC


def _sqlite_runtime_type(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, datetime):
        return "DATETIME"
    if isinstance(value, date):
        return "DATE"
    if isinstance(value, (dict, list)):
        return "JSON"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "FLOAT"
    if isinstance(value, bytes):
        return "BLOB"
    return "TEXT"


class SQLite3Result(ResultABC):
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        self._columns_cache: dict[str, str] | None = None

    def columns(self) -> dict[str, str]:
        if self._columns_cache is None:
            self._columns_cache = self._describe()
        return dict(self._columns_cache)

    def _describe(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self._cursor.description:
            for desc in self._cursor.description:
                result[desc[0]] = "NULL"
        return result

    def _observe_row(self, row: Any) -> None:
        if self._columns_cache is None:
            self._columns_cache = self._describe()
        for name in self._columns_cache:
            self._columns_cache[name] = _sqlite_runtime_type(row[name])

    def fetch_dict(self) -> dict[str, Any] | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        self._observe_row(row)
        return dict(row)

    def fetch_dicts(self) -> list[dict[str, Any]]:
        rows = self._cursor.fetchall()
        if rows:
            self._observe_row(rows[0])
        elif self._columns_cache is None:
            self._columns_cache = self._describe()
        return [dict(row) for row in rows]
