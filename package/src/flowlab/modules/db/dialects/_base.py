from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query.enums import TypeEnum

if TYPE_CHECKING:
    from flowlab.modules.db import QueryWithParams
    from flowlab.modules.db.query import OnConflict
    from flowlab.modules.db.query.ddl import AlterABC, Column, ConstraintABC
    from flowlab.modules.db.query.expressions import SqlABC


class DialectABC(ABC):
    on_conflict: bool
    returning: bool
    index_if_not_exists: bool

    def __init__(self, version: str = "0", options: dict[str, Any] | None = None) -> None:
        self._version_str = version
        self._version = self._parse_version(version)
        self._options = options or {}

    @staticmethod
    def _parse_version(version: str) -> int:
        parts = version.split(".")

        def _to_int(s: str) -> int:
            num = ""
            for ch in s:
                if ch.isdigit():
                    num += ch
                else:
                    break
            return int(num) if num else 0

        major = _to_int(parts[0]) if len(parts) > 0 else 0
        minor = _to_int(parts[1]) if len(parts) > 1 else 0
        patch = _to_int(parts[2]) if len(parts) > 2 else 0
        return major * 10000 + minor * 100 + patch

    @property
    def version(self) -> str:
        return self._version_str

    @property
    def version_int(self) -> int:
        return self._version

    @property
    def options(self) -> dict[str, Any]:
        return dict(self._options)

    def option(self, key: str, default: Any = None) -> Any:
        return self._options.get(key, default)

    @abstractmethod
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
    ) -> QueryWithParams: ...

    @abstractmethod
    def insert(
        self,
        table: Any,
        values: list[dict[str, Any]],
        on_conflict: OnConflict | None,
        returning: list[str] | None,
        last_insert_id: str | None,
    ) -> QueryWithParams: ...

    @abstractmethod
    def update(
        self,
        table: Any,
        updates: dict[str, Any],
        where: list[Any] | None,
        returning: list[str] | None,
    ) -> QueryWithParams: ...

    @abstractmethod
    def delete(
        self,
        table: Any,
        where: list[Any] | None,
        returning: list[str] | None,
    ) -> QueryWithParams: ...

    @abstractmethod
    def create_table(
        self,
        if_not_exists: bool,
        table: Any,
        columns: list[Column],
        primary_keys: list[str] | None,
        constraints: list[ConstraintABC] | None,
    ) -> QueryWithParams: ...

    @abstractmethod
    def alter_table(
        self,
        table: Any,
        alters: list[AlterABC],
    ) -> list[QueryWithParams]: ...

    @abstractmethod
    def drop_table(
        self,
        if_exists: bool,
        table: Any,
    ) -> QueryWithParams: ...

    @abstractmethod
    def create_index(
        self,
        if_not_exists: bool,
        name: str | list[str],
        table: Any,
        columns: list[Any],
        unique: bool,
    ) -> QueryWithParams: ...

    @abstractmethod
    def drop_index(
        self,
        if_exists: bool,
        name: str | list[str],
        table: Any,
    ) -> QueryWithParams: ...

    @abstractmethod
    def list_tables(self, schema: str) -> QueryWithParams: ...

    @abstractmethod
    def describe_table_columns(self, table: Any) -> QueryWithParams: ...

    @abstractmethod
    def describe_table_constraints(self, table: Any) -> QueryWithParams: ...

    @abstractmethod
    def describe_table_indexes(self, table: Any) -> QueryWithParams: ...

    @abstractmethod
    def begin_transaction(self, name: str | None = None) -> QueryWithParams: ...

    @abstractmethod
    def commit_transaction(self, name: str | None = None) -> QueryWithParams: ...

    @abstractmethod
    def rollback_transaction(self, name: str | None = None) -> QueryWithParams: ...

    @abstractmethod
    def begin_savepoint(self, name: str) -> QueryWithParams: ...

    @abstractmethod
    def commit_savepoint(self, name: str) -> QueryWithParams: ...

    @abstractmethod
    def rollback_savepoint(self, name: str) -> QueryWithParams: ...

    @abstractmethod
    def escape_identifier(self, identifier: str | list[Any] | SqlABC) -> str: ...

    @abstractmethod
    def escape_string(self, string: str) -> str: ...

    @abstractmethod
    def cast_to_query(self, value: Any) -> str: ...

    @abstractmethod
    def cast_bool(self, value: bool) -> bool | int: ...

    @abstractmethod
    def cast_datetime(self, value: Any) -> str: ...

    @abstractmethod
    def cast_json(self, value: Any) -> str: ...

    @abstractmethod
    def cast_to_driver(self, value: Any) -> Any: ...

    @abstractmethod
    def parse_bool(self, value: Any) -> bool: ...

    @abstractmethod
    def parse_datetime(self, value: Any) -> Any: ...

    @abstractmethod
    def parse_json(self, value: Any) -> Any: ...

    @abstractmethod
    def type(self, type_enum: TypeEnum, size: int | None = None) -> str: ...

    @abstractmethod
    def parse_type(self, sql_type: str) -> tuple[TypeEnum | str, int | None]: ...

    @abstractmethod
    def parse_default(self, default_expression: str, type_enum: TypeEnum | str) -> Any: ...

    def parse_column_type(self, sql_type: str, auto_increment: bool) -> tuple[TypeEnum | str, int | None]:
        return self.parse_type(sql_type)
