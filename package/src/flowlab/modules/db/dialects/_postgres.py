from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from flowlab.modules.db._query_with_params import QueryWithParams
from flowlab.modules.db.dialects._sql_dialect import SQLDialect
from flowlab.modules.db.query import Condition, OnConflict
from flowlab.modules.db.query.ddl import Column
from flowlab.modules.db.query.enums import ConditionEnum, TypeEnum
from flowlab.modules.db.query.expressions import PostgresArray

_TZ_OFFSET_RE = re.compile(r"([+-]\d{2})$")

_DEFAULT_CAST = re.compile(r"::[A-Za-z_][A-Za-z0-9_ ]*(?:\[\])*$")

_NAIVE_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


class PostgresqlDialect(SQLDialect):
    escape_chars: ClassVar[Mapping[str, str]] = {
        "\\": "\\\\",
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
        "\0": "",
        "\b": "\\b",
        "\x1a": "\\x1A",
        "\f": "\\f",
        "\v": "\\v",
    }

    def __init__(self, version: str = "16", options: dict[str, Any] | None = None) -> None:
        super().__init__(version=version, options=options)
        self.bool = True
        self.distinct_on = True
        self.on_conflict = True
        self.returning = True
        self.lateral = True
        self.datetime_format = "%Y-%m-%d %H:%M:%S.%f%z"
        self._version_gate()

    default_schema_sql: ClassVar[str] = "current_schema"

    def _version_gate(self) -> None:
        v = self._version
        self.distinct_on = v >= 70200
        self.lateral = v >= 90300
        self.on_conflict = v >= 90500
        self.generated_by_default_as_identity = v >= 170000
        self.returning = v >= 80200
        self.json = v >= 90200
        self.jsonb = v >= 90400
        self.index_if_not_exists = v >= 90500
        self.index_if_exists = v >= 80200

    def _build_on_conflict(
        self,
        query: list[str],
        params: list[Any],
        on_conflict: OnConflict | None,
        values: list[dict[str, Any]],
        last_insert_id: str | None,
    ) -> str:
        if on_conflict is None:
            return ""

        conflict = on_conflict.conflict

        if isinstance(conflict, str):
            query.append(f" ON CONFLICT ON CONSTRAINT {self.escape_identifier(conflict)}")
            self._build_on_conflict_action(query, params, on_conflict, values)
        else:
            super()._build_on_conflict(query, params, on_conflict, values, last_insert_id)

        return ""

    def _build_condition_like(self, query: list[str], params: list[Any], cond: Condition) -> None:
        identifier_sql = self._escape_or_sql(cond.identifier)
        if cond.condition == ConditionEnum.LIKE:
            operator = "ILIKE" if cond.case_insensitive else "LIKE"
        else:
            operator = "NOT ILIKE" if cond.case_insensitive else "NOT LIKE"
        query.append(f"{identifier_sql} {operator} ")
        self._build_question_marks(query, params, cond.value)

    def _build_condition_regex(self, query: list[str], params: list[Any], cond: Condition) -> None:
        use_tilde = self.option("use_tilde_regex", False)
        if self._version >= 150000 and not use_tilde:
            super()._build_condition_regex(query, params, cond)
            return

        self._build_condition_regex_operator(query, params, cond, "~", "!~")

    def _build_column(self, col: Column) -> str:
        if not col.auto_increment:
            return super()._build_column(col)

        if self.generated_by_default_as_identity and not self.option("use_serials", True):
            return super()._build_column(col)

        sql_type = col.type
        if isinstance(sql_type, TypeEnum):
            sql_type = self.type(sql_type, col.size)

        type_is_uppercase = any(ch.isupper() for ch in sql_type)
        upper_type = sql_type.upper()
        if upper_type in ("SMALLINT", "INTEGER", "INT", "INT2", "INT4"):
            serial_type = "SERIAL" if type_is_uppercase else "serial"
        elif upper_type in ("BIGINT", "INT8"):
            serial_type = "BIGSERIAL" if type_is_uppercase else "bigserial"
        else:
            serial_type = sql_type

        serial_col = dataclasses.replace(col, type=serial_type, auto_increment=False, default=None)
        return super()._build_column(serial_col)

    def list_tables(self, schema: str) -> QueryWithParams:
        query = (
            "SELECT c.relname AS table_name"
            " FROM pg_class c"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = ? AND c.relkind IN ('r', 'p')"
            " ORDER BY c.relname"
        )

        return QueryWithParams(query=query, params=[schema])

    def describe_table_columns(self, table: Any) -> QueryWithParams:
        identity_sql = "a.attidentity <> ''" if self._version >= 100000 else "FALSE"

        query = (
            "SELECT"
            " a.attname AS column_name,"
            " format_type(a.atttypid, a.atttypmod) AS column_type,"
            " a.attnotnull AS not_null,"
            " pg_get_expr(d.adbin, d.adrelid) AS default_expression,"
            f" ({identity_sql}"
            " OR COALESCE(POSITION('nextval(' IN pg_get_expr(d.adbin, d.adrelid)) = 1, FALSE))"
            " AS auto_increment"
            " FROM pg_attribute a"
            " LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum"
            " WHERE a.attrelid = to_regclass(?) AND a.attnum > 0 AND NOT a.attisdropped"
            " ORDER BY a.attnum"
        )

        return QueryWithParams(query=query, params=[self._table_name(table)])

    def describe_table_constraints(self, table: Any) -> QueryWithParams:
        action = (
            "CASE {column}"
            " WHEN 'a' THEN 'NO ACTION'"
            " WHEN 'r' THEN 'RESTRICT'"
            " WHEN 'c' THEN 'CASCADE'"
            " WHEN 'n' THEN 'SET NULL'"
            " WHEN 'd' THEN 'SET DEFAULT'"
            " END"
        )

        query = (
            "SELECT"
            " con.oid AS constraint_id,"
            " con.conname AS constraint_name,"
            " CASE con.contype WHEN 'u' THEN 'UNIQUE' WHEN 'p' THEN 'PRIMARY KEY'"
            " ELSE 'FOREIGN KEY' END AS constraint_type,"
            " att.attname AS column_name,"
            " cols.ord AS column_position,"
            " ref_cls.relname AS ref_table,"
            " ref_att.attname AS ref_column,"
            f" {action.format(column='con.confdeltype')} AS on_delete,"
            f" {action.format(column='con.confupdtype')} AS on_update"
            " FROM pg_constraint con"
            " CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS cols(attnum, ord)"
            " JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = cols.attnum"
            " LEFT JOIN pg_class ref_cls ON ref_cls.oid = con.confrelid"
            " LEFT JOIN pg_attribute ref_att"
            " ON ref_att.attrelid = con.confrelid AND ref_att.attnum = con.confkey[cols.ord::int]"
            " WHERE con.conrelid = to_regclass(?) AND con.contype IN ('p', 'u', 'f')"
            " ORDER BY con.conname, cols.ord"
        )

        return QueryWithParams(query=query, params=[self._table_name(table)])

    def describe_table_indexes(self, table: Any) -> QueryWithParams:
        # INCLUDE columns are not key columns, and only 11 and up can tell them apart.
        key_columns = "i.indnkeyatts" if self._version >= 110000 else "i.indnatts"

        query = (
            "SELECT"
            " i.indexrelid AS index_id,"
            " cls.relname AS index_name,"
            " att.attname AS column_name,"
            " cols.pos + 1 AS column_position,"
            " CASE WHEN i.indisunique THEN 1 ELSE 0 END AS is_unique,"
            " CASE WHEN i.indpred IS NOT NULL THEN 1 ELSE 0 END AS is_partial"
            " FROM pg_index i"
            " JOIN pg_class cls ON cls.oid = i.indexrelid"
            " JOIN pg_am am ON am.oid = cls.relam"
            f" CROSS JOIN LATERAL generate_series(0, {key_columns} - 1) AS cols(pos)"
            " LEFT JOIN pg_attribute att"
            " ON att.attrelid = i.indrelid AND att.attnum = i.indkey[cols.pos]"
            " WHERE i.indrelid = to_regclass(?) AND NOT i.indisprimary"
            " AND am.amname = 'btree'"
            " AND NOT EXISTS (SELECT 1 FROM pg_constraint con WHERE con.conindid = i.indexrelid)"
            " ORDER BY cls.relname, cols.pos"
        )

        return QueryWithParams(query=query, params=[self._table_name(table)])

    def cast_to_query(self, value: Any) -> str:
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"

        if isinstance(value, PostgresArray):
            if not value.values:
                return "'{}'"
            items = ", ".join(self.cast_to_query(item) for item in value.values)
            return f"ARRAY[{items}]"

        return super().cast_to_query(value)

    def cast_to_driver(self, value: Any) -> Any:
        if isinstance(value, PostgresArray):
            return list(value.values)

        return super().cast_to_driver(value)

    def cast_bool(self, value: bool) -> bool | int:
        return value

    def cast_datetime(self, value: Any) -> str:
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return super().cast_datetime(value)

    def parse_datetime(self, value: Any) -> Any:
        if isinstance(value, str):
            value = _TZ_OFFSET_RE.sub(r"\1:00", value)
            try:
                return datetime.strptime(value, self.datetime_format)  # noqa: DTZ007
            except ValueError:
                pass
            try:
                return datetime.strptime(value, _NAIVE_DATETIME_FORMAT).replace(tzinfo=UTC)
            except ValueError:
                pass
        return super().parse_datetime(value)

    def _parse_type_name(self, name: str, size: int | None) -> tuple[TypeEnum, int | None] | None:
        if name == "double precision":
            return TypeEnum.FLOAT, 64
        if name == "real":
            return TypeEnum.FLOAT, 32
        if name in ("timestamptz", "timestamp with time zone", "timestamp without time zone", "timestamp"):
            return TypeEnum.DATETIME, size

        return super()._parse_type_name(name, size)

    def _parse_default_literal(self, expression: str) -> tuple[str, bool]:
        return super()._parse_default_literal(_DEFAULT_CAST.sub("", expression).strip())

    def type(self, type_enum: TypeEnum, size: int | None = None) -> str:
        width = size or 0
        if type_enum == TypeEnum.FLOAT:
            return "DOUBLE PRECISION" if width > 32 else "REAL"
        if type_enum == TypeEnum.DATETIME:
            return "TIMESTAMPTZ"
        if type_enum == TypeEnum.JSON and self.jsonb:
            return "JSONB"
        return super().type(type_enum, size)
