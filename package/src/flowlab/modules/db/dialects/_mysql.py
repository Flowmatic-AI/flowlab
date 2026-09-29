from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, ClassVar

from flowlab.modules.db._query_with_params import QueryWithParams
from flowlab.modules.db.dialects._sql_dialect import SQLDialect
from flowlab.modules.db.query import Condition, OnConflict
from flowlab.modules.db.query.ddl import AlterColumn, Column, ConstraintABC, DropConstraint
from flowlab.modules.db.query.enums import ConditionEnum, TypeEnum
from flowlab.modules.db.query.expressions import CurrentTimestamp, Excluded, Raw, SqlABC, Values


class MySQLDialect(SQLDialect):
    # DATETIME(6) / TIMESTAMP(3) etc. -- captures the fractional seconds precision.
    FRACTIONAL_DATETIME: ClassVar[re.Pattern[str]] = re.compile(
        r"^\s*(?:DATETIME|TIMESTAMP)\s*\(\s*(\d+)\s*\)\s*$", re.IGNORECASE
    )

    CAST_TYPES: ClassVar[Mapping[str, str]] = {
        "bool": "UNSIGNED",
        "int": "SIGNED",
        "float": "DECIMAL",
        "string": "CHAR",
    }

    escape_chars: ClassVar[Mapping[str, str]] = {
        "\\": "\\\\",
        "\n": "\\n",
        "\r": "\\r",
        "\t": "\\t",
        "\0": "\\0",
        "\b": "\\b",
        "\x1a": "\\Z",
        "'": "\\'",
    }

    def __init__(self, version: str = "8.0.0", options: dict[str, Any] | None = None, is_mariadb: bool = False) -> None:
        super().__init__(version=version, options=options)
        self.bool = False
        self.distinct_on = False
        self.on_conflict = False
        self.returning = False
        self.lateral = False
        self.savepoints = True
        self.generated_by_default_as_identity = False
        self.escape_identifier_char = "`"
        self.escape_string_char = '"'
        self.escape_ansi = False
        self.datetime_format = "%Y-%m-%d %H:%M:%S.%f"
        self._is_mariadb = is_mariadb
        self._version_gate()

    default_schema_sql: ClassVar[str] = "DATABASE()"

    def _version_gate(self) -> None:
        self.lateral = (not self._is_mariadb) and self._version >= 80014
        self.on_conflict = True if self._is_mariadb else self._version >= 40100
        self.returning = self._is_mariadb and self._version >= 100500
        self.json = self._version >= 100207 if self._is_mariadb else self._version >= 50708
        self.index_if_not_exists = self._is_mariadb and self._version >= 100104
        self.index_if_exists = self._is_mariadb and self._version >= 100104

    def begin_transaction(self, name: str | None = None) -> QueryWithParams:
        return QueryWithParams(query="START TRANSACTION")

    def commit_transaction(self, name: str | None = None) -> QueryWithParams:
        return QueryWithParams(query="COMMIT")

    def rollback_transaction(self, name: str | None = None) -> QueryWithParams:
        return QueryWithParams(query="ROLLBACK")

    def create_table(
        self,
        if_not_exists: bool,
        table: Any,
        columns: list[Column],
        primary_keys: list[str] | None = None,
        constraints: list[ConstraintABC] | None = None,
    ) -> QueryWithParams:
        merged_primary_keys = list(primary_keys) if primary_keys else []
        for col in columns:
            if not col.auto_increment:
                continue
            if col.name not in merged_primary_keys:
                merged_primary_keys.append(col.name)

        return super().create_table(if_not_exists, table, columns, merged_primary_keys, constraints)

    def drop_index(self, if_exists: bool, name: str | list[str], table: Any) -> QueryWithParams:
        qwp = super().drop_index(if_exists, name, table)
        return QueryWithParams(query=f"{qwp.query} ON {self._table_name(table)}")

    def _index_name(self, name: str | list[str], table: Any) -> str | list[str]:
        return name

    def list_tables(self, schema: str) -> QueryWithParams:
        query = (
            "SELECT t.TABLE_NAME AS table_name"
            " FROM information_schema.TABLES t"
            " WHERE t.TABLE_TYPE = 'BASE TABLE' AND t.TABLE_SCHEMA = DATABASE()"
            " ORDER BY t.TABLE_NAME"
        )

        return QueryWithParams(query=query)

    def describe_table_columns(self, table: Any) -> QueryWithParams:
        schema, name = self._schema_and_table(table)
        params: list[Any] = [name]
        schema_filter = self._schema_filter("c.TABLE_SCHEMA", schema, params)

        query = (
            "SELECT"
            " c.COLUMN_NAME AS column_name,"
            " c.COLUMN_TYPE AS column_type,"
            " CASE WHEN c.IS_NULLABLE = 'NO' THEN 1 ELSE 0 END AS not_null,"
            " c.COLUMN_DEFAULT AS default_expression,"
            " CASE WHEN LOCATE('auto_increment', c.EXTRA) > 0 THEN 1 ELSE 0 END AS auto_increment"
            " FROM information_schema.COLUMNS c"
            f" WHERE c.TABLE_NAME = ?{schema_filter}"
            " ORDER BY c.ORDINAL_POSITION"
        )

        return QueryWithParams(query=query, params=params)

    def describe_table_constraints(self, table: Any) -> QueryWithParams:
        schema, name = self._schema_and_table(table)
        params: list[Any] = [name]
        schema_filter = self._schema_filter("tc.table_schema", schema, params)

        query = (
            "SELECT"
            " tc.constraint_name AS constraint_id,"
            " tc.constraint_name AS constraint_name,"
            " tc.constraint_type AS constraint_type,"
            " kcu.column_name AS column_name,"
            " kcu.ordinal_position AS column_position,"
            " kcu.referenced_table_name AS ref_table,"
            " kcu.referenced_column_name AS ref_column,"
            " rc.delete_rule AS on_delete,"
            " rc.update_rule AS on_update"
            " FROM information_schema.table_constraints tc"
            " JOIN information_schema.key_column_usage kcu"
            " ON kcu.constraint_schema = tc.constraint_schema"
            " AND kcu.constraint_name = tc.constraint_name"
            " AND kcu.table_name = tc.table_name"
            " LEFT JOIN information_schema.referential_constraints rc"
            " ON rc.constraint_schema = tc.constraint_schema"
            " AND rc.constraint_name = tc.constraint_name"
            " AND rc.table_name = tc.table_name"
            f" WHERE tc.table_name = ?{schema_filter}"
            " AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')"
            " ORDER BY tc.constraint_name, kcu.ordinal_position"
        )

        return QueryWithParams(query=query, params=params)

    def _build_on_conflict(
        self,
        query: list[str],
        params: list[Any],
        on_conflict: OnConflict | None,
        values: list[dict[str, Any]],
        last_insert_id: str | None,
    ) -> str:
        if not self.on_conflict:
            return ""

        if on_conflict is None:
            return ""

        insert_ignore = on_conflict.updates is None

        if insert_ignore and not last_insert_id:
            assert query[0] == "INSERT INTO ", "Expected query to start with 'INSERT INTO '"
            query[0] = "INSERT IGNORE INTO "
            return ""

        updates: dict[str, Any] = {}
        if not insert_ignore:
            if on_conflict.updates:
                updates = dict(on_conflict.updates)
            else:
                columns: list[str] = []
                for val_set in values:
                    for col in val_set:
                        if col not in columns:
                            columns.append(col)
                updates = {col: Values() for col in columns}

        if last_insert_id is not None:
            updates[last_insert_id] = Raw(f"LAST_INSERT_ID({self.escape_identifier(last_insert_id)})")

        sets: list[str] = []
        for col, val in updates.items():
            esc = self.escape_identifier(col)
            if isinstance(val, Excluded):
                if val.identifier is not None:
                    sets.append(f"{esc} = VALUES({self.escape_identifier(val.identifier)})")
                else:
                    sets.append(f"{esc} = VALUES({esc})")
            elif isinstance(val, SqlABC):
                sets.append(f"{esc} = {val.raw_sql(self)}")
            else:
                val_q: list[str] = []
                val_p: list[Any] = []
                self._build_question_marks(val_q, val_p, val)
                sets.append(f"{esc} = {''.join(val_q)}")
                params.extend(val_p)

        query.append(" ON DUPLICATE KEY UPDATE ")
        query.append(", ".join(sets))

        return ""

    def _build_returning(self, query: list[str], returning: list[str] | None) -> None:
        if query and query[0].startswith("UPDATE"):
            return
        super()._build_returning(query, returning)

    def _build_condition_like(self, query: list[str], params: list[Any], cond: Condition) -> None:
        if self._version < 40000:
            super()._build_condition_like(query, params, cond)
            return

        identifier_sql = self._escape_or_sql(cond.identifier)
        if cond.condition == ConditionEnum.LIKE:
            operator = "LIKE" if cond.case_insensitive else "LIKE BINARY"
        else:
            operator = "NOT LIKE" if cond.case_insensitive else "NOT LIKE BINARY"
        query.append(f"{identifier_sql} {operator} ")
        self._build_question_marks(query, params, cond.value)

    def _build_condition_regex(self, query: list[str], params: list[Any], cond: Condition) -> None:
        use_regexp_option = self.option("use_regexp", False)
        if not self._is_mariadb and self._version >= 80000 and not use_regexp_option:
            super()._build_condition_regex(query, params, cond)
            return

        self._build_condition_regex_operator(query, params, cond, "REGEXP", "NOT REGEXP")

    def _build_column(self, col: Column) -> str:
        sql = super()._build_column(col)
        if col.auto_increment:
            sql += " AUTO_INCREMENT"
        return sql

    def _build_column_default(self, default: Any, sql_type: str) -> str:
        if isinstance(default, CurrentTimestamp):
            match = self.FRACTIONAL_DATETIME.match(sql_type)
            if match:
                return f"DEFAULT CURRENT_TIMESTAMP({match.group(1)})"

        return super()._build_column_default(default, sql_type)

    def _build_alter_table_alter_column(self, alter: AlterColumn) -> str:
        # MySQL restates the column definition under MODIFY COLUMN rather than
        # naming the attribute to change after ALTER COLUMN.
        return f"MODIFY COLUMN {self.escape_identifier(alter.column)} {alter.sql}"

    def _build_alter_table_drop_constraint(self, alter: DropConstraint) -> str:
        return f"DROP INDEX {self.escape_identifier(alter.name)}"

    def _parse_type_name(self, name: str, size: int | None) -> tuple[TypeEnum, int | None] | None:
        name = name.removesuffix(" zerofill").removesuffix(" unsigned")

        if name == "tinyint":
            return TypeEnum.BOOL, None
        if name == "double":
            return TypeEnum.FLOAT, 64
        if name == "float":
            return TypeEnum.FLOAT, 32
        if name == "text":
            return TypeEnum.STRING, 65535
        if name == "mediumtext":
            return TypeEnum.STRING, 16777215
        if name == "longtext":
            return TypeEnum.STRING, 4294967295
        if name == "timestamp":
            return TypeEnum.DATETIME, size

        return super()._parse_type_name(name, size)

    def _parse_default_literal(self, expression: str) -> tuple[str, bool]:
        return expression, True

    def type(self, type_enum: TypeEnum, size: int | None = None) -> str:
        width = size or 0
        if type_enum == TypeEnum.BOOL:
            return "TINYINT"
        if type_enum == TypeEnum.FLOAT:
            return "DOUBLE" if width > 32 else "FLOAT"
        if type_enum == TypeEnum.STRING:
            if width > 16777215:
                return "LONGTEXT"
            if width > 65535:
                return "MEDIUMTEXT"
            if width > 255:
                return "TEXT"
            return f"VARCHAR({size or 255})"
        if type_enum == TypeEnum.DATETIME:
            if width <= 0:
                return "DATETIME"
            return f"DATETIME({min(width, 6)})"
        return super().type(type_enum, size)
