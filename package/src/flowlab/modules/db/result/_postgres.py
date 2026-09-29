from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from flowlab.modules.db.result._base import ResultABC


class PsycopgResult(ResultABC):
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor
        self._columns_cache: dict[str, str] | None = None

    def columns(self) -> dict[str, str]:
        if self._columns_cache is not None:
            return dict(self._columns_cache)
        result: dict[str, str] = {}
        if self._cursor.description:
            for desc in self._cursor.description:
                name = desc.name
                type_code = desc.type_code
                type_name = _PG_TYPE_NAMES.get(type_code, "text")
                result[name] = type_name
        self._columns_cache = result
        return dict(result)

    def fetch_dict(self) -> dict[str, Any] | None:
        row = self._cursor.fetchone()
        if row is None:
            return None
        if self._columns_cache is None:
            self.columns()
        if self._columns_cache:
            return dict(zip(self._columns_cache.keys(), row))
        return dict(row)

    def fetch_dicts(self) -> list[dict[str, Any]]:
        rows = self._cursor.fetchall()
        if self._columns_cache is None:
            self.columns()
        if not self._columns_cache:
            return [dict(r) for r in rows]
        cols = list(self._columns_cache.keys())
        return [dict(zip(cols, row)) for row in rows]


class AsyncpgResult(ResultABC):
    """asyncpg fetches are coroutines, so rows are already materialised by the
    adapter before the result is handed back to the caller."""

    def __init__(self, attributes: Sequence[Any], records: Sequence[Any]) -> None:
        self._columns: dict[str, str] = {
            attribute.name: _PG_TYPE_NAMES.get(attribute.type.oid, "text") for attribute in attributes
        }
        self._rows: list[dict[str, Any]] = [dict(record) for record in records]

    def columns(self) -> dict[str, str]:
        return dict(self._columns)

    def fetch_dict(self) -> dict[str, Any] | None:
        if not self._rows:
            return None
        return self._rows.pop(0)

    def fetch_dicts(self) -> list[dict[str, Any]]:
        rows = list(self._rows)
        self._rows.clear()
        return rows


_PG_TYPE_NAMES: dict[int, str] = {
    16: "bool",
    17: "bytea",
    18: "char",
    19: "name",
    20: "bigint",
    21: "smallint",
    22: "int2vector",
    23: "integer",
    24: "regproc",
    25: "text",
    26: "oid",
    27: "tid",
    28: "xid",
    29: "cid",
    114: "json",
    142: "xml",
    143: "xml",
    194: "pg_node_tree",
    600: "point",
    601: "lseg",
    602: "path",
    603: "box",
    604: "polygon",
    628: "line",
    700: "real",
    701: "double precision",
    702: "abstime",
    703: "reltime",
    704: "tinterval",
    705: "unknown",
    718: "circle",
    790: "money",
    829: "macaddr",
    869: "inet",
    650: "cidr",
    1000: "boolean[]",
    1001: "bytea[]",
    1003: "name[]",
    1005: "smallint[]",
    1007: "integer[]",
    1009: "text[]",
    1014: "bpchar[]",
    1015: "varchar[]",
    1016: "bigint[]",
    1017: "point[]",
    1018: "lseg[]",
    1019: "path[]",
    1020: "box[]",
    1021: "float4[]",
    1022: "float8[]",
    1023: "abstime[]",
    1024: "reltime[]",
    1025: "tinterval[]",
    1027: "circle[]",
    1028: "inet[]",
    1033: "aclitem",
    1040: "macaddr[]",
    1041: "aclitem[]",
    1042: "bpchar",
    1043: "varchar",
    1082: "date",
    1083: "time",
    1114: "timestamp",
    1184: "timestamptz",
    1186: "interval",
    1266: "timetz",
    1560: "bit",
    1562: "varbit",
    1700: "numeric",
    2275: "cstring",
    2276: "trigger",
    2280: "void",
    2281: "internal",
    2283: "any",
    2776: "anyelement",
    2950: "uuid",
    2970: "txid_snapshot",
    3220: "pg_lsn",
    3361: "pg_ndistinct",
    3402: "pg_dependencies",
    3500: "anyenum",
    3614: "tsvector",
    3615: "tsquery",
    3642: "gtsvector",
    3734: "regconfig",
    3769: "regdictionary",
    3802: "jsonb",
    3904: "int4range",
    3906: "numrange",
    3908: "tsrange",
    3910: "tstzrange",
    3912: "daterange",
    3926: "int8range",
    4072: "jsonpath",
    4480: "regnamespace",
    4481: "regoper",
    4482: "regoperator",
    4483: "regproc",
    4484: "regprocedure",
    4485: "regclass",
    4486: "regtype",
    4487: "regrole",
    4500: "xid8",
    4600: "pg_brin_bloom_summary",
    4601: "pg_brin_minmax_multi_summary",
    5000: "pg_wal_summary",
}
