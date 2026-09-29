from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from flowlab.modules.db._json import decode_json
from flowlab.modules.db.result._base import ResultABC

_MYSQL_JSON_TYPE_CODE = 245
_MYSQL_TINYINT_TYPE_CODE = 1


class MySQLResult(ResultABC):
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        self._columns_cache: dict[str, str] | None = None
        self._json_indexes: list[int] = []
        self._bool_indexes: list[int] = []

    def columns(self) -> dict[str, str]:
        if self._columns_cache is not None:
            return dict(self._columns_cache)
        result: dict[str, str] = {}
        json_indexes: list[int] = []
        bool_indexes: list[int] = []
        if self._cursor.description:
            for index, desc in enumerate(self._cursor.description):
                name = desc[0]
                type_code = desc[1]
                type_name = _MYSQL_TYPE_NAMES.get(type_code, "unknown")
                result[name] = type_name
                if type_code == _MYSQL_JSON_TYPE_CODE:
                    json_indexes.append(index)
                if type_code == _MYSQL_TINYINT_TYPE_CODE:
                    bool_indexes.append(index)
        self._columns_cache = result
        self._json_indexes = json_indexes
        self._bool_indexes = bool_indexes
        return dict(result)

    def _decode_row(self, row: Sequence[Any]) -> list[Any]:
        """mysql.connector hands JSON columns back as the raw stored text (str
        or bytes); DATETIME/TIMESTAMP columns already arrive as datetimes.

        MySQL has no boolean type either: ``TypeEnum.BOOL`` is a TINYINT, which
        the wire protocol reports without its display width -- so every TINYINT
        column reads back as a bool. TypeEnum.INT never maps to TINYINT, so this
        only ever touches columns this library would have written as booleans.
        """
        if not self._json_indexes and not self._bool_indexes:
            return list(row)
        values = list(row)
        for index in self._json_indexes:
            if index < len(values):
                values[index] = decode_json(values[index])
        for index in self._bool_indexes:
            if index < len(values) and values[index] is not None:
                values[index] = bool(values[index])
        return values

    def fetch_dict(self) -> dict[str, Any] | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        if self._columns_cache is None:
            self.columns()
        if self._columns_cache:
            return dict(zip(self._columns_cache.keys(), self._decode_row(row)))
        return dict(row)

    def fetch_dicts(self) -> list[dict[str, Any]]:
        rows = self._cursor.fetchall()
        if self._columns_cache is None:
            self.columns()
        if not self._columns_cache:
            return [dict(r) for r in rows]
        cols = list(self._columns_cache.keys())
        return [dict(zip(cols, self._decode_row(row))) for row in rows]


_MYSQL_TYPE_NAMES: dict[int, str] = {
    0: "decimal",
    1: "tinyint",
    2: "smallint",
    3: "integer",
    4: "float",
    5: "double",
    6: "null",
    7: "timestamp",
    8: "bigint",
    9: "mediumint",
    10: "date",
    11: "time",
    12: "datetime",
    13: "year",
    14: "unknown",
    15: "varchar",
    16: "bit",
    246: "decimal",
    249: "tinyint",
    250: "varchar",
    251: "char",
    252: "blob",
    253: "text",
    254: "string",
    245: "json",
}
