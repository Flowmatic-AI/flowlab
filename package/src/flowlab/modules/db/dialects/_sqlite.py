from __future__ import annotations

import dataclasses
import re
from typing import Any

from flowlab.modules.db import QueryError
from flowlab.modules.db._query_with_params import QueryWithParams
from flowlab.modules.db.dialects._sql_dialect import SQLDialect
from flowlab.modules.db.query import Condition, OnConflict
from flowlab.modules.db.query.ddl import (
    AddForeignKeyConstraint,
    AddPrimaryKeys,
    AddUniqueConstraint,
    AlterColumn,
    Column,
    ConstraintABC,
    DropConstraint,
    ForeignKeyConstraint,
    RenameColumn,
    UniqueConstraint,
)
from flowlab.modules.db.query.enums import ConditionEnum, TypeEnum

_LIKE_ESCAPE_RE = re.compile(r"\\(.)", re.DOTALL)


class SQLiteDialect(SQLDialect):
    def __init__(self, version: str = "3.45", options: dict[str, Any] | None = None) -> None:
        super().__init__(version=version, options=options)
        self.generated_by_default_as_identity = False
        self.escape_identifier_char = '"'
        self.datetime_format = "%Y-%m-%d %H:%M:%S"
        self._version_gate()

    def _version_gate(self) -> None:
        v = self._version
        self.on_conflict = v >= 32400
        self.returning = v >= 33500
        self.savepoints = v >= 30000

    def create_table(
        self,
        if_not_exists: bool,
        table: Any,
        columns: list[Column],
        primary_keys: list[str] | None = None,
        constraints: list[ConstraintABC] | None = None,
    ) -> QueryWithParams:
        auto_increment_names = {col.name for col in columns if col.auto_increment}
        filtered_primary_keys = [pk for pk in (primary_keys or []) if pk not in auto_increment_names]

        return super().create_table(if_not_exists, table, columns, filtered_primary_keys, constraints)

    def create_index(
        self,
        if_not_exists: bool,
        name: str | list[str],
        table: Any,
        columns: list[Any],
        unique: bool = False,
    ) -> QueryWithParams:
        _, table_name = self._schema_and_table(table)
        return super().create_index(if_not_exists, self._index_name(name, table), table_name, columns, unique)

    def list_tables(self, schema: str) -> QueryWithParams:
        query = (
            "SELECT m.name AS table_name"
            " FROM sqlite_master m"
            " WHERE m.type = 'table' AND SUBSTR(m.name, 1, 7) <> 'sqlite_'"
            " ORDER BY m.name"
        )

        return QueryWithParams(query=query)

    def describe_table_columns(self, table: Any) -> QueryWithParams:
        schema, name = self._schema_and_table(table)

        master = "sqlite_master" if schema is None else f"{self.escape_identifier(schema)}.sqlite_master"
        table_info = "pragma_table_info(?)" if schema is None else "pragma_table_info(?, ?)"
        params: list[Any] = [name, name] if schema is None else [name, name, schema]

        query = (
            "SELECT"
            " ti.name AS column_name,"
            " ti.type AS column_type,"
            ' ti."notnull" AS not_null,'
            " ti.dflt_value AS default_expression,"
            " CASE WHEN ti.pk = 1 AND UPPER(ti.type) = 'INTEGER' AND EXISTS ("
            f" SELECT 1 FROM {master} m"
            " WHERE m.type = 'table' AND m.name = ? AND INSTR(UPPER(m.sql), 'AUTOINCREMENT') > 0"
            " ) THEN 1 ELSE 0 END AS auto_increment"
            f" FROM {table_info} AS ti"
            " ORDER BY ti.cid"
        )

        return QueryWithParams(query=query, params=params)

    def describe_table_constraints(self, table: Any) -> QueryWithParams:
        schema, name = self._schema_and_table(table)

        params: list[Any]
        if schema is None:
            table_info = "pragma_table_info(?)"
            index_list = "pragma_index_list(?)"
            index_info = "pragma_index_info(il.name)"
            foreign_key_list = "pragma_foreign_key_list(?)"
            params = [name, name, name]
        else:
            table_info = "pragma_table_info(?, ?)"
            index_list = "pragma_index_list(?, ?)"
            index_info = "pragma_index_info(il.name, ?)"
            foreign_key_list = "pragma_foreign_key_list(?, ?)"
            params = [name, schema, name, schema, schema, name, schema]

        query = (
            "SELECT"
            " 'p' AS constraint_id,"
            " NULL AS constraint_name,"
            " 'PRIMARY KEY' AS constraint_type,"
            " ti.name AS column_name,"
            " ti.pk AS column_position,"
            " NULL AS ref_table,"
            " NULL AS ref_column,"
            " NULL AS on_delete,"
            " NULL AS on_update"
            f" FROM {table_info} AS ti"
            " WHERE ti.pk > 0"
            " UNION ALL"
            " SELECT"
            " 'u:' || il.name,"
            " il.name,"
            " 'UNIQUE',"
            " ii.name,"
            " ii.seqno + 1,"
            " NULL,"
            " NULL,"
            " NULL,"
            " NULL"
            f" FROM {index_list} AS il"
            f" JOIN {index_info} AS ii"
            " WHERE il.\"unique\" = 1 AND il.origin = 'u'"
            " UNION ALL"
            " SELECT"
            " 'f:' || fk.id,"
            " NULL,"
            " 'FOREIGN KEY',"
            ' fk."from",'
            " fk.seq + 1,"
            ' fk."table",'
            ' fk."to",'
            " fk.on_delete,"
            " fk.on_update"
            f" FROM {foreign_key_list} AS fk"
            " ORDER BY 1, 5"
        )

        return QueryWithParams(query=query, params=params)

    def describe_table_indexes(self, table: Any) -> QueryWithParams:
        schema, name = self._schema_and_table(table)

        params: list[Any]
        if schema is None:
            index_list = "pragma_index_list(?)"
            index_info = "pragma_index_info(il.name)"
            params = [name]
        else:
            index_list = "pragma_index_list(?, ?)"
            index_info = "pragma_index_info(il.name, ?)"
            params = [name, schema, schema]

        query = (
            "SELECT"
            " il.name AS index_id,"
            " il.name AS index_name,"
            " ii.name AS column_name,"
            " ii.seqno + 1 AS column_position,"
            ' il."unique" AS is_unique,'
            ' il."partial" AS is_partial'
            f" FROM {index_list} AS il"
            f" JOIN {index_info} AS ii"
            " WHERE il.origin = 'c'"
            " ORDER BY il.name, ii.seqno"
        )

        return QueryWithParams(query=query, params=params)

    @staticmethod
    def _like_to_glob(like_pattern: str) -> str:
        glob_escape: dict[str, str | int | None] = {"*": "[*]", "?": "[?]", "[": "[[]", "]": "[]]"}
        glob_pattern = like_pattern.translate(str.maketrans(glob_escape))

        if "\\" in glob_pattern:

            def _unescape(match: re.Match[str]) -> str:
                return {"%": "[%]", "_": "[_]", "\\": "[\\]"}.get(match.group(1), match.group(1))

            glob_pattern = _LIKE_ESCAPE_RE.sub(_unescape, glob_pattern)

        wildcard_swap: dict[str, str | int | None] = {"%": "*", "_": "?"}
        return glob_pattern.translate(str.maketrans(wildcard_swap))

    def _build_condition_like(self, query: list[str], params: list[Any], cond: Condition) -> None:
        identifier_sql = self._escape_or_sql(cond.identifier)

        if cond.condition == ConditionEnum.LIKE:
            operator = "LIKE" if cond.case_insensitive else "GLOB"
        else:
            operator = "NOT LIKE" if cond.case_insensitive else "NOT GLOB"

        value = cond.value if cond.case_insensitive else self._like_to_glob(cond.value)

        query.append(f"{identifier_sql} {operator} ")
        self._build_question_marks(query, params, value)

    def _build_condition_glob(self, query: list[str], params: list[Any], cond: Condition) -> None:
        identifier_sql = self._escape_or_sql(cond.identifier)

        value_parts: list[str] = []
        self._build_question_marks(value_parts, params, cond.value)
        value_sql = "".join(value_parts)

        if cond.case_insensitive:
            identifier_sql = f"lower({identifier_sql})"
            value_sql = f"lower({value_sql})"

        operator = "NOT GLOB" if cond.condition == ConditionEnum.NOT_GLOB else "GLOB"
        query.append(f"{identifier_sql} {operator} {value_sql}")

    def _build_condition_regex(self, query: list[str], params: list[Any], cond: Condition) -> None:
        if not self.option("use_regexp", False):
            super()._build_condition_regex(query, params, cond)
            return

        self._build_condition_regex_operator(query, params, cond, "REGEXP", "NOT REGEXP")

    def _build_on_conflict(
        self,
        query: list[str],
        params: list[Any],
        on_conflict: OnConflict | None,
        values: list[dict[str, Any]],
        last_insert_id: str | None,
    ) -> str:
        if on_conflict is not None and isinstance(on_conflict.conflict, str):
            raise QueryError("Named ON CONFLICT constraints are not supported by SQLite")

        return super()._build_on_conflict(query, params, on_conflict, values, last_insert_id)

    def _build_column(self, col: Column) -> str:
        if col.auto_increment:
            return f"{self.escape_identifier(col.name)} INTEGER PRIMARY KEY AUTOINCREMENT"

        return super()._build_column(col)

    def _build_unique_constraint(self, constraint: UniqueConstraint) -> str:
        return super()._build_unique_constraint(dataclasses.replace(constraint, name=None))

    def _build_foreign_key_constraint(self, constraint: ForeignKeyConstraint) -> str:
        return super()._build_foreign_key_constraint(dataclasses.replace(constraint, name=None))

    def _build_alter_table_alter_column(self, alter: AlterColumn) -> str:
        raise QueryError("SQLite does not support altering columns")

    def _build_alter_table_rename_column(self, alter: RenameColumn) -> str:
        if self._version < 32500:
            raise QueryError("SQLite does not support renaming columns before 3.25.0")
        return super()._build_alter_table_rename_column(alter)

    def _build_alter_table_add_primary_keys(self, alter: AddPrimaryKeys) -> str:
        raise QueryError("Constraint alteration (add_primary_key) is not supported by SQLite")

    def _build_alter_table_add_unique_constraint(self, alter: AddUniqueConstraint) -> str:
        raise QueryError("Constraint alteration (add_unique) is not supported by SQLite")

    def _build_alter_table_add_foreign_key_constraint(self, alter: AddForeignKeyConstraint) -> str:
        raise QueryError("Constraint alteration (add_foreign_key) is not supported by SQLite")

    def _build_alter_table_drop_constraint(self, alter: DropConstraint) -> str:
        raise QueryError("Constraint alteration (drop_constraint) is not supported by SQLite")

    def parse_column_type(self, sql_type: str, auto_increment: bool) -> tuple[TypeEnum | str, int | None]:
        parsed_type, size = super().parse_column_type(sql_type, auto_increment)

        if auto_increment and parsed_type == TypeEnum.INT:
            return parsed_type, 64

        return parsed_type, size

    def _parse_type_name(self, name: str, size: int | None) -> tuple[TypeEnum, int | None] | None:
        if name == "real":
            return TypeEnum.FLOAT, 64

        return super()._parse_type_name(name, size)

    def type(self, type_enum: TypeEnum, size: int | None = None) -> str:
        if type_enum == TypeEnum.BOOL:
            return "BOOLEAN"
        if type_enum == TypeEnum.FLOAT:
            return "REAL"
        return super().type(type_enum, size)
