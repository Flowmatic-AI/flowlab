from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from typing import Any, ClassVar
from uuid import UUID

from flowlab.modules.db import QueryError
from flowlab.modules.db._json import decode_json, encode_json
from flowlab.modules.db._query_with_params import QueryWithParams
from flowlab.modules.db.dialects._base import DialectABC
from flowlab.modules.db.query import Condition, ConditionGroupABC, Join, OnConflict, OrderBy, SelectQuery, Union
from flowlab.modules.db.query.ddl import (
    AddColumn,
    AddForeignKeyConstraint,
    AddPrimaryKeys,
    AddUniqueConstraint,
    AlterABC,
    AlterColumn,
    Column,
    ConstraintABC,
    DropColumn,
    DropConstraint,
    ForeignKeyConstraint,
    RawAlter,
    RawConstraint,
    RenameColumn,
    UniqueConstraint,
)
from flowlab.modules.db.query.enums import ChainEnum, ConditionEnum, TypeEnum
from flowlab.modules.db.query.expressions import Alias, CurrentTimestamp, Excluded, PostgresArray, Raw, SqlABC

_TRAILING_ZEROS = re.compile(r"(\.[0-9]+?)0+$")

_DECLARED_TYPE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 ]*?)\s*(?:\(\s*(\d+)\s*(?:,\s*\d+\s*)?\))?\s*$")

_CURRENT_TIMESTAMP_DEFAULT = re.compile(r"^(?:CURRENT_TIMESTAMP(?:\s*\(\s*\d+\s*\))?|NOW\s*\(\s*\))$", re.IGNORECASE)

_TRUE_DEFAULTS = ("true", "t", "1", "yes")
_FALSE_DEFAULTS = ("false", "f", "0", "no")


def _format_float_for_query(value: float) -> str:
    formatted = f"{value:.53f}"
    return _TRAILING_ZEROS.sub(r"\1", formatted)


def _debug_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


class SQLDialect(DialectABC):
    def __init__(self, version: str = "0", options: dict[str, Any] | None = None) -> None:
        super().__init__(version=version, options=options)
        self.bool = False
        self.distinct_on = False
        self.on_conflict = False
        self.returning = False
        self.lateral = False
        self.savepoints = True
        self.json = True
        self.jsonb = False
        self.index_if_not_exists = True
        self.index_if_exists = True
        self.generated_by_default_as_identity = True
        self.escape_identifier_char = '"'
        self.escape_string_char = "'"
        self.escape_ansi = True
        self.datetime_format = "%Y-%m-%d %H:%M:%S"

    def begin_transaction(self, name: str | None = None) -> QueryWithParams:
        return QueryWithParams(query="BEGIN TRANSACTION")

    def commit_transaction(self, name: str | None = None) -> QueryWithParams:
        return QueryWithParams(query="COMMIT TRANSACTION")

    def rollback_transaction(self, name: str | None = None) -> QueryWithParams:
        return QueryWithParams(query="ROLLBACK TRANSACTION")

    def begin_savepoint(self, name: str) -> QueryWithParams:
        return QueryWithParams(query=f"SAVEPOINT {self.escape_identifier(name)}")

    def commit_savepoint(self, name: str) -> QueryWithParams:
        return QueryWithParams(query=f"RELEASE SAVEPOINT {self.escape_identifier(name)}")

    def rollback_savepoint(self, name: str) -> QueryWithParams:
        return QueryWithParams(query=f"ROLLBACK TO SAVEPOINT {self.escape_identifier(name)}")

    def select(
        self,
        distinct: list[str] | None,
        columns: list[Any] | None,
        table: Any,
        joins: list[Any] | None,
        where: list[Any] | None,
        group_by: list[str] | None,
        having: list[Any] | None,
        order_by: list[Any] | None,
        limit: int | None,
        offset: int | None,
        unions: list[Any] | None,
    ) -> QueryWithParams:
        needs_wrapping = bool(unions)

        query_parts: list[str] = []
        params: list[Any] = []

        if needs_wrapping:
            query_parts.append("(")

        query_parts.append("SELECT")
        self._build_distinct(query_parts, distinct)
        self._build_columns(query_parts, params, columns)
        self._build_table(query_parts, params, table)
        self._build_joins(query_parts, params, joins)
        self._build_where(query_parts, params, where)
        self._build_group_by(query_parts, group_by)
        self._build_having(query_parts, params, having)
        self._build_order_by(query_parts, order_by)
        self._build_limit(query_parts, limit)
        self._build_offset(query_parts, offset)

        if needs_wrapping:
            query_parts.append(")")

        self._build_unions(query_parts, params, unions)

        return QueryWithParams(query="".join(query_parts), params=params)

    def _build_distinct(self, query: list[str], distinct: list[str] | None) -> None:
        if distinct is None:
            return
        if not distinct:
            query.append(" DISTINCT")
        elif self.distinct_on:
            query.append(f" DISTINCT ON ({', '.join(self.escape_identifier(c) for c in distinct)})")
        else:
            raise QueryError("DISTINCT ON is not supported by this dialect")

    def _build_columns(self, query: list[str], params: list[Any], columns: list[Any] | None) -> None:
        if not columns:
            query.append(" *")
        else:
            col_parts = []
            for col in columns:
                if isinstance(col, SqlABC):
                    col_parts.append(col.sql(self))
                    params.extend(col.params(self))
                else:
                    col_parts.append(self.escape_identifier(col))
            query.append(" " + ", ".join(col_parts))

    def _build_table(self, query: list[str], params: list[Any], table: Any) -> None:
        if table is None:
            return
        query.append(" FROM ")
        if isinstance(table, SqlABC):
            query.append(table.raw_sql(self))
            params.extend(table.params(self))
        elif isinstance(table, str):
            query.append(self.escape_identifier(table))
        elif isinstance(table, list):
            query.append(".".join(self.escape_identifier(t) for t in table))
        else:
            query.append(str(table))

    def _build_joins(self, query: list[str], params: list[Any], joins: list[Any] | None) -> None:
        if not joins:
            return
        for join_spec in joins:
            if isinstance(join_spec, SqlABC):
                query.append(" " + join_spec.raw_sql(self))
                params.extend(join_spec.params(self))
            elif isinstance(join_spec, Join):
                query.append(f" {join_spec.join.value} ")
                query.append(self._table_name(join_spec.table))
                query.append(" ON ")
                if len(join_spec.conditions) > 0:
                    for i, cond in enumerate(join_spec.conditions):
                        if i > 0:
                            query.append(self._chain_connector(cond))
                        self._build_condition(query, params, cond)
                else:
                    query.append(self.cast_to_query(True))

    def _build_where(self, query: list[str], params: list[Any], where: list[Any] | None) -> None:
        if not where:
            return
        query.append(" WHERE ")
        for i, cond in enumerate(where):
            if i > 0:
                query.append(self._chain_connector(cond))
            self._build_condition(query, params, cond)

    def _build_having(self, query: list[str], params: list[Any], having: list[Any] | None) -> None:
        if not having:
            return
        query.append(" HAVING ")
        for i, cond in enumerate(having):
            if i > 0:
                query.append(self._chain_connector(cond))
            self._build_condition(query, params, cond)

    def _build_group_by(self, query: list[str], group_by: list[str] | None) -> None:
        if not group_by:
            return
        query.append(" GROUP BY " + ", ".join(self.escape_identifier(c) for c in group_by))

    def _build_order_by(self, query: list[str], order_by: list[Any] | None) -> None:
        if not order_by:
            return
        parts = []
        for ob in order_by:
            if isinstance(ob, OrderBy):
                parts.append(f"{self.escape_identifier(ob.column)} {ob.direction.value}")
            elif isinstance(ob, SqlABC):
                parts.append(ob.raw_sql(self))
            else:
                parts.append(str(ob))
        query.append(" ORDER BY " + ", ".join(parts))

    def _build_limit(self, query: list[str], limit: int | None) -> None:
        if limit is not None:
            query.append(f" LIMIT {limit}")

    def _build_offset(self, query: list[str], offset: int | None) -> None:
        if offset is not None:
            query.append(f" OFFSET {offset}")

    def _build_unions(self, query: list[str], params: list[Any], unions: list[Any] | None) -> None:
        if not unions:
            return
        for union_spec in unions:
            if isinstance(union_spec, Union):
                qwp = union_spec.select_query.to_query_with_params()
                query.append(f" {union_spec.union.value} ({qwp.query})")
                params.extend(qwp.params)

    def _escape_or_sql(self, identifier: Any) -> str:
        if isinstance(identifier, SqlABC):
            return identifier.raw_sql(self)
        if isinstance(identifier, list):
            parts: list[str] = []
            for part in identifier:
                parts.extend(self.escape_identifier(str(seg)) for seg in str(part).split("."))
            return ".".join(parts)
        return self.escape_identifier(str(identifier))

    def _chain_connector(self, condition: Any) -> str:
        if condition.chain == ChainEnum.OR:
            return " OR "
        return " AND "

    def _build_condition(self, query: list[str], params: list[Any], condition: Any) -> None:
        if isinstance(condition, ConditionGroupABC):
            self._build_condition_group(query, params, condition)
        elif isinstance(condition, Condition):
            self._build_single_condition(query, params, condition)
        elif isinstance(condition, SqlABC):
            query.append(condition.sql(self))
            params.extend(condition.params(self))
        else:
            query.append(str(condition))

    def _build_condition_group(self, query: list[str], params: list[Any], group: ConditionGroupABC) -> None:
        conds = group.conditions
        if not conds:
            return
        if group.not_:
            query.append("NOT (")
        else:
            query.append("(")
        for i, cond in enumerate(conds):
            if i > 0:
                query.append(self._chain_connector(cond))
            self._build_condition(query, params, cond)
        query.append(")")

    def _build_single_condition(self, query: list[str], params: list[Any], cond: Condition) -> None:
        if isinstance(cond.condition, ConditionEnum):
            condition_type = cond.condition
        else:
            query.append(self._escape_or_sql(cond.identifier))
            query.append(f" {cond.condition} ")
            self._build_question_marks(query, params, cond.value)
            return

        if condition_type == ConditionEnum.RAW:
            if isinstance(cond.value, SqlABC):
                query.append(cond.value.raw_sql(self))
            else:
                query.append(str(cond.value))
        elif condition_type == ConditionEnum.EQUALS:
            self._build_condition_equals(query, params, cond)
        elif condition_type == ConditionEnum.NOT_EQUALS:
            self._build_condition_not_equals(query, params, cond)
        elif condition_type in (ConditionEnum.BETWEEN, ConditionEnum.NOT_BETWEEN):
            self._build_condition_between(query, params, cond)
        elif condition_type in (ConditionEnum.LIKE, ConditionEnum.NOT_LIKE):
            self._build_condition_like(query, params, cond)
        elif condition_type in (ConditionEnum.GLOB, ConditionEnum.NOT_GLOB):
            self._build_condition_glob(query, params, cond)
        elif condition_type in (ConditionEnum.IN, ConditionEnum.NOT_IN):
            self._build_condition_in(query, params, cond)
        elif condition_type in (ConditionEnum.REGEX, ConditionEnum.NOT_REGEX):
            self._build_condition_regex(query, params, cond)
        elif condition_type in (ConditionEnum.EXISTS, ConditionEnum.NOT_EXISTS):
            self._build_condition_exists(query, params, cond)
        else:
            query.append(self._escape_or_sql(cond.identifier))
            query.append(f" {cond.condition.value} ")
            self._build_question_marks(query, params, cond.value)

    def _build_condition_equals(self, query: list[str], params: list[Any], cond: Condition) -> None:
        self._build_equality(query, params, cond, is_not=False)

    def _build_condition_not_equals(self, query: list[str], params: list[Any], cond: Condition) -> None:
        self._build_equality(query, params, cond, is_not=True)

    def _build_equality(self, query: list[str], params: list[Any], cond: Condition, is_not: bool) -> None:
        identifier_sql = self._escape_or_sql(cond.identifier)
        operator = "<>" if is_not else "="

        if cond.value is None:
            query.append(identifier_sql)
            query.append(" IS NOT NULL" if is_not else " IS NULL")
            return

        if not cond.cast:
            query.append(identifier_sql)
            query.append(f" {operator} ")
            self._build_question_marks(query, params, cond.value)
            return

        if isinstance(cond.value, (list, SqlABC)):
            query.append(identifier_sql)
            query.append(f" {operator} ")
            query.append(self._escape_or_sql(cond.value))
            return

        cast_type = self._cast_type_for_value(cond.value)

        if cast_type is None:
            query.append(identifier_sql)
            query.append(f" {operator} ")
            self._build_question_marks(query, params, cond.value)
            return

        query.append(f"cast({identifier_sql} AS {cast_type}) {operator} cast(")
        self._build_question_marks(query, params, cond.value)
        query.append(f" AS {cast_type})")

    CAST_TYPES: ClassVar[Mapping[str, str]] = {}

    def _cast_type_for_value(self, value: Any) -> str | None:
        debug_type = _debug_type_name(value)
        override = self.CAST_TYPES.get(debug_type)
        if override is not None:
            return override
        if isinstance(value, bool):
            return self.type(TypeEnum.BOOL)
        if isinstance(value, int):
            return self.type(TypeEnum.INT, 64)
        if isinstance(value, float):
            return self.type(TypeEnum.FLOAT, 64)
        if isinstance(value, str):
            return self.type(TypeEnum.STRING, sys.maxsize)
        if isinstance(value, datetime):
            return self.type(TypeEnum.DATETIME, 6)
        return None

    def _build_condition_between(self, query: list[str], params: list[Any], cond: Condition) -> None:
        query.append(self._escape_or_sql(cond.identifier))
        prefix = " NOT " if cond.condition == ConditionEnum.NOT_BETWEEN else " "
        query.append(f"{prefix}BETWEEN ")
        if isinstance(cond.value, (list, tuple)) and len(cond.value) >= 2:
            self._build_question_marks(query, params, cond.value[0])
            query.append(" AND ")
            self._build_question_marks(query, params, cond.value[1])

    def _build_condition_like(self, query: list[str], params: list[Any], cond: Condition) -> None:
        identifier_sql = self._escape_or_sql(cond.identifier)

        value_parts: list[str] = []
        self._build_question_marks(value_parts, params, cond.value)
        value_sql = "".join(value_parts)

        if cond.case_insensitive:
            identifier_sql = f"lower({identifier_sql})"
            value_sql = f"lower({value_sql})"

        operator = "NOT LIKE" if cond.condition == ConditionEnum.NOT_LIKE else "LIKE"
        query.append(f"{identifier_sql} {operator} {value_sql}")

    def _build_condition_glob(self, query: list[str], params: list[Any], cond: Condition) -> None:
        like_condition = Condition(
            condition=ConditionEnum.NOT_LIKE if cond.condition == ConditionEnum.NOT_GLOB else ConditionEnum.LIKE,
            identifier=cond.identifier,
            value=self._glob_to_like(cond.value),
            chain=cond.chain,
            case_insensitive=cond.case_insensitive,
        )
        self._build_condition_like(query, params, like_condition)

    @staticmethod
    def _glob_to_like(glob_pattern: str) -> str:
        translation: dict[str, str | int | None] = {"\\": "\\\\", "%": "\\%", "_": "\\_", "*": "%", "?": "_"}
        return glob_pattern.translate(str.maketrans(translation))

    def _build_condition_in(self, query: list[str], params: list[Any], cond: Condition) -> None:
        is_not = cond.condition == ConditionEnum.NOT_IN

        if not isinstance(cond.value, SelectQuery) and not cond.value:
            query.append("1 = 1" if is_not else "1 = 0")
            return

        query.append(self._escape_or_sql(cond.identifier))
        query.append(" NOT IN " if is_not else " IN ")

        if isinstance(cond.value, SelectQuery):
            qwp = cond.value.to_query_with_params()
            query.append(f"({qwp.query})")
            params.extend(qwp.params)
            return

        query.append("(")
        for i, val in enumerate(cond.value):
            if i > 0:
                query.append(", ")
            self._build_question_marks(query, params, val)
        query.append(")")

    def _build_condition_regex(self, query: list[str], params: list[Any], cond: Condition) -> None:
        if cond.condition == ConditionEnum.NOT_REGEX:
            query.append("NOT ")
        query.append("regexp_like(")
        query.append(self._escape_or_sql(cond.identifier))
        query.append(", ")
        self._build_question_marks(query, params, cond.value)
        query.append(", ")
        self._build_question_marks(query, params, cond.flags or "")
        query.append(")")

    def _build_condition_regex_operator(
        self,
        query: list[str],
        params: list[Any],
        cond: Condition,
        equals_operator: str,
        not_equals_operator: str,
    ) -> None:
        query.append(self._escape_or_sql(cond.identifier))
        query.append(f" {equals_operator if cond.condition == ConditionEnum.REGEX else not_equals_operator} ")
        pattern = cond.value
        if cond.flags:
            pattern = f"(?{cond.flags}){cond.value}"
        self._build_question_marks(query, params, pattern)

    def _build_condition_exists(self, query: list[str], params: list[Any], cond: Condition) -> None:
        prefix = "NOT " if cond.condition == ConditionEnum.NOT_EXISTS else ""
        query.append(f"{prefix}EXISTS (")
        if isinstance(cond.value, SqlABC):
            query.append(cond.value.raw_sql(self))
            params.extend(cond.value.params(self))
        elif isinstance(cond.value, SelectQuery):
            qwp = cond.value.to_query_with_params()
            query.append(qwp.query)
            params.extend(qwp.params)
        query.append(")")

    def _build_question_marks(self, query: list[str], params: list[Any], value: Any) -> None:
        if value is None:
            params.append(None)
            query.append("?")
        elif isinstance(value, SelectQuery):
            qwp = value.to_query_with_params()
            query.append(f"({qwp.query})")
            params.extend(qwp.params)
        elif isinstance(value, SqlABC):
            query.append(value.sql(self))
            params.extend(value.params(self))
        else:
            params.append(value)
            query.append("?")

    def insert(
        self,
        table: Any,
        values: list[dict[str, Any]],
        on_conflict: OnConflict | None = None,
        returning: list[str] | None = None,
        last_insert_id: str | None = None,
    ) -> QueryWithParams:
        query_parts = ["INSERT INTO "]
        params: list[Any] = []

        query_parts.append(self._table_name(table))

        if not values:
            raise QueryError("INSERT requires at least one value set")

        columns: list[str] = []
        for val_set in values:
            for col in val_set:
                if col not in columns:
                    columns.append(col)

        query_parts.append(" (" + ", ".join(self.escape_identifier(c) for c in columns) + ")")
        query_parts.append(" VALUES")

        for vi, val_set in enumerate(values):
            if vi > 0:
                query_parts.append(",")
            query_parts.append(" (")
            for ci, col in enumerate(columns):
                if ci > 0:
                    query_parts.append(", ")
                if col not in val_set:
                    self._build_question_marks(query_parts, params, Raw("DEFAULT"))
                else:
                    self._build_question_marks(query_parts, params, val_set[col])
            query_parts.append(")")

        self._build_on_conflict(query_parts, params, on_conflict, values, last_insert_id)
        self._build_returning(query_parts, returning)

        return QueryWithParams(query="".join(query_parts), params=params)

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

        conflict = on_conflict.conflict

        if isinstance(conflict, str):
            query.append(f" ON CONFLICT ON CONSTRAINT {self.escape_identifier(conflict)}")
        else:
            query.append(f" ON CONFLICT ({', '.join(self.escape_identifier(c) for c in conflict)})")

        self._build_on_conflict_action(query, params, on_conflict, values)
        return ""

    def _build_on_conflict_action(
        self,
        query: list[str],
        params: list[Any],
        on_conflict: OnConflict | None,
        values: list[dict[str, Any]],
    ) -> None:
        if on_conflict is None:
            return

        if on_conflict.updates is None:
            query.append(" DO NOTHING")
            return

        if not on_conflict.updates:
            columns: list[str] = []
            for val_set in values:
                for col in val_set:
                    if col not in columns:
                        columns.append(col)

            query.append(" DO UPDATE SET ")
            sets = [f"{self.escape_identifier(col)} = EXCLUDED.{self.escape_identifier(col)}" for col in columns]
            query.append(", ".join(sets))
            return

        query.append(" DO UPDATE SET ")
        update_sets: list[str] = []
        for col, val in on_conflict.updates.items():
            esc_col = self.escape_identifier(col)
            if isinstance(val, Excluded):
                if val.identifier is not None:
                    update_sets.append(f"{esc_col} = EXCLUDED.{self.escape_identifier(val.identifier)}")
                else:
                    update_sets.append(f"{esc_col} = EXCLUDED.{esc_col}")
            else:
                val_q: list[str] = []
                val_p: list[Any] = []
                self._build_question_marks(val_q, val_p, val)
                update_sets.append(f"{esc_col} = {''.join(val_q)}")
                params.extend(val_p)
        query.append(", ".join(update_sets))

    def _build_returning(self, query: list[str], returning: list[str] | None) -> None:
        if not self.returning:
            return

        if returning is None:
            return

        columns = ", ".join(self.escape_identifier(c) for c in returning) if returning else "*"
        query.append(f" RETURNING {columns}")

    def update(
        self,
        table: Any,
        updates: dict[str, Any],
        where: list[Any] | None = None,
        returning: list[str] | None = None,
    ) -> QueryWithParams:
        if not updates:
            raise QueryError("UPDATE requires at least one column to update")

        query_parts = ["UPDATE "]
        params: list[Any] = []

        query_parts.append(self._table_name(table))

        query_parts.append(" SET ")
        first = True
        for col, val in updates.items():
            if not first:
                query_parts.append(", ")
            first = False
            query_parts.append(f"{self.escape_identifier(col)} = ")
            self._build_question_marks(query_parts, params, val)

        self._build_where(query_parts, params, where)
        self._build_returning(query_parts, returning)

        return QueryWithParams(query="".join(query_parts), params=params)

    def delete(
        self,
        table: Any,
        where: list[Any] | None = None,
        returning: list[str] | None = None,
    ) -> QueryWithParams:
        query_parts = ["DELETE FROM "]
        params: list[Any] = []

        query_parts.append(self._table_name(table))

        self._build_where(query_parts, params, where)
        self._build_returning(query_parts, returning)

        return QueryWithParams(query="".join(query_parts), params=params)

    def create_table(
        self,
        if_not_exists: bool,
        table: Any,
        columns: list[Column],
        primary_keys: list[str] | None = None,
        constraints: list[ConstraintABC] | None = None,
    ) -> QueryWithParams:
        if not columns:
            raise QueryError("CREATE TABLE requires at least one column")

        query_parts = ["CREATE TABLE "]
        if if_not_exists:
            query_parts.append("IF NOT EXISTS ")

        query_parts.append(self._table_name(table))

        query_parts.append(" (\n")
        col_defs: list[str] = []
        has_auto_increment_pk = False

        for col in columns:
            col_def = self._build_column(col)
            if col.auto_increment and "PRIMARY KEY" in col_def.upper():
                has_auto_increment_pk = True
            col_defs.append("  " + col_def)

        if primary_keys and not has_auto_increment_pk:
            col_defs.append(f"  PRIMARY KEY ({', '.join(self.escape_identifier(k) for k in primary_keys)})")

        if constraints:
            for constraint in constraints:
                col_defs.append("  " + self._build_constraint(constraint))

        query_parts.append(",\n".join(col_defs))
        query_parts.append("\n)")

        return QueryWithParams(query="".join(query_parts))

    def _build_column(self, col: Column) -> str:
        parts = [self.escape_identifier(col.name)]

        sql_type = col.type
        if isinstance(sql_type, TypeEnum):
            sql_type = self.type(sql_type, col.size)
        parts.append(sql_type)

        if col.not_null:
            parts.append("NOT NULL")

        if col.auto_increment:
            if self.generated_by_default_as_identity:
                parts.append("GENERATED BY DEFAULT AS IDENTITY")
        elif col.default is not None:
            parts.append(self._build_column_default(col.default, sql_type))

        return " ".join(parts)

    def _build_column_default(self, default: Any, sql_type: str) -> str:
        if isinstance(default, bool):
            return f"DEFAULT {self.cast_bool(default)}"
        if isinstance(default, int):
            return f"DEFAULT {default}"
        if isinstance(default, str):
            return f"DEFAULT {self.escape_string(default)}"
        if isinstance(default, SqlABC):
            return f"DEFAULT {default.raw_sql(self)}"
        return f"DEFAULT {default}"

    def _build_constraint(self, constraint: ConstraintABC) -> str:
        if isinstance(constraint, SqlABC):
            return constraint.raw_sql(self)
        if isinstance(constraint, UniqueConstraint):
            return self._build_unique_constraint(constraint)
        if isinstance(constraint, ForeignKeyConstraint):
            return self._build_foreign_key_constraint(constraint)
        if isinstance(constraint, RawConstraint):
            return constraint.sql
        raise QueryError(f"Unsupported constraint type: {type(constraint).__name__}")

    def _build_unique_constraint(self, constraint: UniqueConstraint) -> str:
        name = constraint.name
        name_part = f"CONSTRAINT {self.escape_identifier(name)} " if name else ""
        return f"{name_part}UNIQUE ({', '.join(self.escape_identifier(c) for c in constraint.columns)})"

    def _build_foreign_key_constraint(self, constraint: ForeignKeyConstraint) -> str:
        name = constraint.name
        name_part = f"CONSTRAINT {self.escape_identifier(name)} " if name else ""
        ref_cols = ", ".join(self.escape_identifier(c) for c in constraint.ref_columns)
        parts = [
            f"{name_part}FOREIGN KEY ({', '.join(self.escape_identifier(c) for c in constraint.columns)})",
            f"REFERENCES {self.escape_identifier(constraint.ref_table)} ({ref_cols})",
        ]
        if constraint.on_delete:
            parts.append(f"ON DELETE {constraint.on_delete}")
        if constraint.on_update:
            parts.append(f"ON UPDATE {constraint.on_update}")
        return " ".join(parts)

    def alter_table(self, table: Any, alters: list[AlterABC]) -> list[QueryWithParams]:
        if not alters:
            raise QueryError("ALTER TABLE requires at least one alter")

        return [self._build_alter(table, alter) for alter in alters]

    def _build_alter(self, table: Any, alter: AlterABC) -> QueryWithParams:
        table_str = self._table_name(table)

        if isinstance(alter, AddColumn):
            fragment = self._build_alter_table_add_column(alter)
        elif isinstance(alter, AlterColumn):
            fragment = self._build_alter_table_alter_column(alter)
        elif isinstance(alter, RenameColumn):
            fragment = self._build_alter_table_rename_column(alter)
        elif isinstance(alter, DropColumn):
            fragment = self._build_alter_table_drop_column(alter)
        elif isinstance(alter, AddPrimaryKeys):
            fragment = self._build_alter_table_add_primary_keys(alter)
        elif isinstance(alter, AddUniqueConstraint):
            fragment = self._build_alter_table_add_unique_constraint(alter)
        elif isinstance(alter, AddForeignKeyConstraint):
            fragment = self._build_alter_table_add_foreign_key_constraint(alter)
        elif isinstance(alter, DropConstraint):
            fragment = self._build_alter_table_drop_constraint(alter)
        elif isinstance(alter, RawAlter):
            fragment = self._build_alter_table_raw(alter)
        else:
            raise QueryError(f"Unsupported alter type: {type(alter).__name__}")

        query = f"ALTER TABLE {table_str}"
        if fragment:
            query += f" {fragment}"

        return QueryWithParams(query=query)

    def _build_alter_table_add_column(self, alter: AddColumn) -> str:
        return f"ADD COLUMN {self._build_column(alter)}"

    def _build_alter_table_alter_column(self, alter: AlterColumn) -> str:
        return f"ALTER COLUMN {self.escape_identifier(alter.column)} {alter.sql}"

    def _build_alter_table_rename_column(self, alter: RenameColumn) -> str:
        return f"RENAME COLUMN {self.escape_identifier(alter.old_name)} TO {self.escape_identifier(alter.new_name)}"

    def _build_alter_table_drop_column(self, alter: DropColumn) -> str:
        return f"DROP COLUMN {self.escape_identifier(alter.column)}"

    def _build_alter_table_add_primary_keys(self, alter: AddPrimaryKeys) -> str:
        return f"ADD PRIMARY KEY ({', '.join(self.escape_identifier(c) for c in alter.columns)})"

    def _build_alter_table_add_unique_constraint(self, alter: AddUniqueConstraint) -> str:
        return f"ADD {self._build_unique_constraint(alter)}"

    def _build_alter_table_add_foreign_key_constraint(self, alter: AddForeignKeyConstraint) -> str:
        return f"ADD {self._build_foreign_key_constraint(alter)}"

    def _build_alter_table_drop_constraint(self, alter: DropConstraint) -> str:
        return f"DROP CONSTRAINT {self.escape_identifier(alter.name)}"

    def _build_alter_table_raw(self, alter: RawAlter) -> str:
        return alter.sql

    def drop_table(self, if_exists: bool, table: Any) -> QueryWithParams:
        table_str = self._table_name(table)
        if if_exists:
            return QueryWithParams(query=f"DROP TABLE IF EXISTS {table_str}")
        return QueryWithParams(query=f"DROP TABLE {table_str}")

    def create_index(
        self,
        if_not_exists: bool,
        name: str | list[str],
        table: Any,
        columns: list[Any],
        unique: bool = False,
    ) -> QueryWithParams:
        if not columns:
            raise QueryError("CREATE INDEX requires at least one column")

        query_parts = ["CREATE "]

        if unique:
            query_parts.append("UNIQUE ")

        query_parts.append("INDEX ")

        if if_not_exists:
            if not self.index_if_not_exists:
                raise QueryError("CREATE INDEX IF NOT EXISTS is not supported by this dialect")
            query_parts.append("IF NOT EXISTS ")

        query_parts.append(self.escape_identifier(name))
        query_parts.append(f" ON {self._table_name(table)}")
        query_parts.append(f" ({', '.join(self.escape_identifier(c) for c in columns)})")

        return QueryWithParams(query="".join(query_parts))

    def drop_index(self, if_exists: bool, name: str | list[str], table: Any) -> QueryWithParams:
        query_parts = ["DROP INDEX "]

        if if_exists:
            if not self.index_if_exists:
                raise QueryError("DROP INDEX IF EXISTS is not supported by this dialect")
            query_parts.append("IF EXISTS ")

        query_parts.append(self.escape_identifier(self._index_name(name, table)))

        return QueryWithParams(query="".join(query_parts))

    def _index_name(self, name: str | list[str], table: Any) -> str | list[str]:
        if isinstance(name, list):
            return name

        schema, _ = self._schema_and_table(table)
        return name if schema is None else [schema, name]

    def list_tables(self, schema: str) -> QueryWithParams:
        params: list[Any] = []
        schema_filter = self._schema_filter("t.table_schema", schema, params)

        query = (
            "SELECT t.table_name AS table_name"
            " FROM information_schema.tables t"
            f" WHERE t.table_type = 'BASE TABLE'{schema_filter}"
            " ORDER BY t.table_name"
        )

        return QueryWithParams(query=query, params=params)

    def describe_table_columns(self, table: Any) -> QueryWithParams:
        schema, name = self._schema_and_table(table)
        params: list[Any] = [name]
        schema_filter = self._schema_filter("c.table_schema", schema, params)

        query = (
            "SELECT"
            " c.column_name AS column_name,"
            " c.data_type AS column_type,"
            " CASE WHEN c.is_nullable = 'NO' THEN 1 ELSE 0 END AS not_null,"
            " c.column_default AS default_expression,"
            " CASE WHEN c.is_identity = 'YES' THEN 1 ELSE 0 END AS auto_increment"
            " FROM information_schema.columns c"
            f" WHERE c.table_name = ?{schema_filter}"
            " ORDER BY c.ordinal_position"
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
            " rkcu.table_name AS ref_table,"
            " rkcu.column_name AS ref_column,"
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
            " LEFT JOIN information_schema.key_column_usage rkcu"
            " ON rkcu.constraint_schema = rc.unique_constraint_schema"
            " AND rkcu.constraint_name = rc.unique_constraint_name"
            " AND rkcu.ordinal_position = kcu.position_in_unique_constraint"
            f" WHERE tc.table_name = ?{schema_filter}"
            " AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')"
            " ORDER BY tc.constraint_name, kcu.ordinal_position"
        )

        return QueryWithParams(query=query, params=params)

    def describe_table_indexes(self, table: Any) -> QueryWithParams:
        schema, name = self._schema_and_table(table)
        params: list[Any] = [name]
        schema_filter = self._schema_filter("s.table_schema", schema, params)

        query = (
            "SELECT"
            " s.index_name AS index_id,"
            " s.index_name AS index_name,"
            " s.column_name AS column_name,"
            " s.seq_in_index AS column_position,"
            " CASE WHEN s.non_unique = 0 THEN 1 ELSE 0 END AS is_unique,"
            " 0 AS is_partial"
            " FROM information_schema.statistics s"
            f" WHERE s.table_name = ?{schema_filter}"
            " AND s.index_type IN ('BTREE', 'HASH')"
            " AND NOT EXISTS ("
            " SELECT 1 FROM information_schema.table_constraints tc"
            " WHERE tc.table_name = s.table_name"
            " AND tc.table_schema = s.table_schema"
            " AND tc.constraint_name = s.index_name"
            " )"
            " ORDER BY s.index_name, s.seq_in_index"
        )

        return QueryWithParams(query=query, params=params)

    default_schema_sql: ClassVar[str | None] = None

    @staticmethod
    def _schema_and_table(table: Any) -> tuple[str | None, str]:
        if isinstance(table, list):
            if len(table) == 1:
                return None, str(table[0])
            if len(table) == 2:
                return str(table[0]), str(table[1])
            raise QueryError("Table introspection expects a table name optionally qualified by one schema")

        if isinstance(table, str):
            return None, table

        raise QueryError(f"Table introspection expects a table name, got: {type(table).__name__}")

    def _schema_filter(self, column: str, schema: str | None, params: list[Any]) -> str:
        if schema is not None:
            params.append(schema)
            return f" AND {column} = ?"

        if self.default_schema_sql is not None:
            return f" AND {column} = {self.default_schema_sql}"

        return ""

    def _table_name(self, table: Any) -> str:
        return self.escape_identifier(table)

    escape_chars: ClassVar[Mapping[str, str]] = {"\0": ""}

    def escape_identifier(self, identifier: str | list[Any] | SqlABC) -> str:
        if isinstance(identifier, Alias):
            return f"{self.escape_identifier(identifier.identifier)} AS {self.escape_identifier(identifier.alias)}"

        if isinstance(identifier, SqlABC):
            return identifier.raw_sql(self)

        # A list is a qualified identifier -- each segment is escaped on its own
        # and joined with dots, so ["schema", "table", "column"] nests as deeply
        # as it needs to.
        if isinstance(identifier, list):
            return ".".join(self.escape_identifier(segment) for segment in identifier)

        return self._escape(str(identifier), self.escape_identifier_char)

    def escape_string(self, string: str) -> str:
        return self._escape(string, self.escape_string_char)

    def _escape(self, string: str, char: str) -> str:
        table = {ord(old): new for old, new in self.escape_chars.items()}
        table[ord(char)] = (char * 2) if self.escape_ansi else f"\\{char}"
        escaped = string.translate(table)
        return f"{char}{escaped}{char}"

    def cast_to_query(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return str(self.cast_bool(value))
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return _format_float_for_query(value)
        if isinstance(value, str):
            return self.escape_string(value)
        if isinstance(value, datetime):
            return self.escape_string(self.cast_datetime(value))
        if isinstance(value, (date, time)):
            return self.escape_string(value.isoformat())
        if isinstance(value, UUID):
            return self.escape_string(str(value))
        if isinstance(value, PostgresArray):
            return self.escape_string(self.cast_json(value.values))
        if isinstance(value, (dict, list)):
            return self.escape_string(self.cast_json(value))
        if isinstance(value, SelectQuery):
            qwp = value.to_query_with_params()
            return f"({qwp.to_sql(self)})"
        if isinstance(value, SqlABC):
            return value.raw_sql(self)
        return str(value)

    def cast_bool(self, value: bool) -> bool | int:
        return 1 if value else 0

    def cast_datetime(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.strftime(self.datetime_format)
        return str(value)

    def cast_json(self, value: Any) -> str:
        return encode_json(value)

    def cast_to_driver(self, value: Any) -> Any:
        if isinstance(value, bool):
            return self.cast_bool(value)
        if isinstance(value, datetime):
            return self.cast_datetime(value)
        if isinstance(value, PostgresArray):
            return self.cast_json(value.values)
        if isinstance(value, (dict, list)):
            return self.cast_json(value)
        return value

    def parse_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.lower() in ("true", "1", "t", "yes")
        return bool(value)

    def parse_datetime(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value, self.datetime_format).replace(tzinfo=UTC)
            except ValueError:
                pass
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value
        return value

    def parse_json(self, value: Any) -> Any:
        return decode_json(value)

    def parse_type(self, sql_type: str) -> tuple[TypeEnum | str, int | None]:
        match = _DECLARED_TYPE.match(sql_type)
        if match is None:
            return sql_type, None

        name = " ".join(match.group(1).split()).lower()
        size = int(match.group(2)) if match.group(2) is not None else None

        parsed = self._parse_type_name(name, size)
        if parsed is None:
            return sql_type, None

        return parsed

    def _parse_type_name(self, name: str, size: int | None) -> tuple[TypeEnum, int | None] | None:
        if name in ("boolean", "bool"):
            return TypeEnum.BOOL, None
        if name in ("smallint", "int2"):
            return TypeEnum.INT, 16
        if name in ("integer", "int", "int4"):
            return TypeEnum.INT, 32
        if name in ("bigint", "int8"):
            return TypeEnum.INT, 64
        if name in ("decimal", "numeric"):
            return TypeEnum.FLOAT, 64 if (size or 0) > 15 else 32
        if name in ("varchar", "character varying"):
            return TypeEnum.STRING, size if size is not None else sys.maxsize
        if name == "text":
            return TypeEnum.STRING, sys.maxsize
        if name == "datetime":
            return TypeEnum.DATETIME, size
        if name in ("json", "jsonb"):
            return TypeEnum.JSON, None

        return None

    def parse_default(self, default_expression: str, type_enum: TypeEnum | str) -> Any:
        expression = default_expression.strip()

        if _CURRENT_TIMESTAMP_DEFAULT.match(expression):
            return CurrentTimestamp()

        if not isinstance(type_enum, TypeEnum):
            return default_expression

        value, is_literal = self._parse_default_literal(expression)

        if type_enum == TypeEnum.STRING:
            return value if is_literal else default_expression

        if type_enum == TypeEnum.BOOL:
            if value.lower() in _TRUE_DEFAULTS:
                return True
            if value.lower() in _FALSE_DEFAULTS:
                return False
            return default_expression

        if type_enum == TypeEnum.INT:
            try:
                return int(value)
            except ValueError:
                return default_expression

        if type_enum == TypeEnum.FLOAT:
            try:
                return float(value)
            except ValueError:
                return default_expression

        if type_enum == TypeEnum.DATETIME:
            parsed = self.parse_datetime(value)
            return parsed if isinstance(parsed, datetime) else default_expression

        if type_enum == TypeEnum.JSON:
            decoded = self.parse_json(value)
            return default_expression if isinstance(decoded, str) else decoded

        return default_expression

    def _parse_default_literal(self, expression: str) -> tuple[str, bool]:
        if len(expression) >= 2 and expression.startswith("'") and expression.endswith("'"):
            return expression[1:-1].replace("''", "'"), True

        return expression, False

    def type(self, type_enum: TypeEnum, size: int | None = None) -> str:
        width = size or 0
        mapping = {
            TypeEnum.BOOL: "BOOLEAN" if self.bool else "INTEGER",
            TypeEnum.INT: "BIGINT" if width > 32 else "INTEGER",
            TypeEnum.FLOAT: "DECIMAL(30, 15)" if width > 32 else "DECIMAL(15, 7)",
            TypeEnum.STRING: "TEXT" if width > 255 else f"VARCHAR({size or 255})",
            TypeEnum.DATETIME: "DATETIME",
            TypeEnum.JSON: "JSON" if self.json else "TEXT",
        }
        return mapping.get(type_enum, f"VARCHAR({size or 255})")
