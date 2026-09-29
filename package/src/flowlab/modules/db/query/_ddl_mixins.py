from __future__ import annotations

import sys
from typing import Any, Self

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
from flowlab.modules.db.query.enums import ReferentialActionEnum, TypeEnum
from flowlab.modules.db.query.expressions import CurrentTimestamp


class IfNotExistsMixin:
    _if_not_exists: bool

    def if_not_exists(self) -> Self:
        self._if_not_exists = True
        return self


class IfExistsMixin:
    _if_exists: bool

    def if_exists(self) -> Self:
        self._if_exists = True
        return self


class PrimaryKeysMixin:
    _primary_keys: list[str]

    def primary_keys(self, columns: str | list[str]) -> Self:
        if isinstance(columns, str):
            columns = [columns]
        self._primary_keys = columns
        return self


class ConstraintsMixin:
    _constraints: list[ConstraintABC]

    def unique_constraint(self, columns: list[Any], name: str | None = None) -> Self:
        self._constraints.append(UniqueConstraint(columns=columns, name=name))
        return self

    def foreign_key_constraint(
        self,
        column: str | list[str],
        ref_table: str,
        ref_column: str | list[str],
        name: str | None = None,
        on_delete: ReferentialActionEnum | str | None = None,
        on_update: ReferentialActionEnum | str | None = None,
    ) -> Self:
        self._constraints.append(
            ForeignKeyConstraint(
                columns=[column] if isinstance(column, str) else list(column),
                ref_table=ref_table,
                ref_columns=[ref_column] if isinstance(ref_column, str) else list(ref_column),
                name=name,
                on_delete=on_delete,
                on_update=on_update,
            )
        )
        return self

    def constraint(self, sql: str) -> Self:
        self._constraints.append(RawConstraint(sql=sql))
        return self


class ColumnsDefinitionMixin:
    _columns: list[Column]

    _primary_keys: list[str]

    def column(
        self,
        name: str,
        type_: TypeEnum | str,
        not_null: bool = False,
        default: Any = None,
        generated_by_default_as_identity: bool = False,
        size: int | None = None,
    ) -> Self:
        self._columns.append(
            Column(
                name=name,
                type=type_,
                size=size,
                not_null=not_null,
                default=default,
                auto_increment=generated_by_default_as_identity,
            )
        )
        return self

    def auto_increment(self, name: str, size: int = 64, add_primary_key: bool = True) -> Self:
        return self.identity(name, size, add_primary_key)

    def serial(self, name: str, size: int = 64, add_primary_key: bool = True) -> Self:
        return self.identity(name, size, add_primary_key)

    def identity(self, name: str, size: int = 64, add_primary_key: bool = True) -> Self:
        if add_primary_key and name not in self._primary_keys:
            self._primary_keys.append(name)
        return self.integer(name, size, True, None, True)

    def boolean(self, name: str, not_null: bool = False, default: bool | None = None) -> Self:
        return self.column(name, TypeEnum.BOOL, not_null, default)

    def integer(
        self,
        name: str,
        size: int = 64,
        not_null: bool = False,
        default: int | None = None,
        generated_by_default_as_identity: bool = False,
    ) -> Self:
        return self.column(name, TypeEnum.INT, not_null, default, generated_by_default_as_identity, size=size)

    def float(
        self,
        name: str,
        size: int = 64,
        not_null: bool = False,
        default: float | None = None,
    ) -> Self:
        return self.column(name, TypeEnum.FLOAT, not_null, default, size=size)

    def string(
        self,
        name: str,
        size: int = 255,
        not_null: bool = False,
        default: str | None = None,
    ) -> Self:
        return self.column(name, TypeEnum.STRING, not_null, default, size=size)

    def text(self, name: str, not_null: bool = False, default: str | None = None) -> Self:
        return self.string(name, sys.maxsize, not_null, default)

    def datetime(
        self,
        name: str,
        size: int = 6,
        not_null: bool = False,
        default: Any = None,
    ) -> Self:
        return self.column(name, TypeEnum.DATETIME, not_null, default, size=size)

    def current_timestamp(
        self,
        name: str,
        size: int = 6,
        not_null: bool = False,
    ) -> Self:
        return self.datetime(name, size, not_null, CurrentTimestamp())

    def json(self, name: str, not_null: bool = False, default: Any = None) -> Self:
        return self.column(name, TypeEnum.JSON, not_null, default)


class AltersMixin:
    _alters: list[AlterABC]

    def add_column(
        self,
        name: str,
        type_: TypeEnum | str,
        not_null: bool = False,
        default: Any = None,
        generated_by_default_as_identity: bool = False,
        size: int | None = None,
    ) -> Self:
        self._alters.append(
            AddColumn(
                name=name,
                type=type_,
                size=size,
                not_null=not_null,
                default=default,
                auto_increment=generated_by_default_as_identity,
            )
        )
        return self

    def alter_column(self, column: str, sql: str) -> Self:
        self._alters.append(AlterColumn(column=column, sql=sql))
        return self

    def rename_column(self, old: str, new: str) -> Self:
        self._alters.append(RenameColumn(old_name=old, new_name=new))
        return self

    def drop_column(self, column: str) -> Self:
        self._alters.append(DropColumn(column=column))
        return self

    def add_primary_keys(self, columns: str | list[str]) -> Self:
        if isinstance(columns, str):
            columns = [columns]
        self._alters.append(AddPrimaryKeys(columns=columns))
        return self

    def add_unique_constraint(self, columns: list[str], name: str | None = None) -> Self:
        self._alters.append(AddUniqueConstraint(columns=columns, name=name))
        return self

    def add_foreign_key_constraint(
        self,
        column: str | list[str],
        ref_table: str,
        ref_column: str | list[str],
        name: str | None = None,
        on_delete: ReferentialActionEnum | str | None = None,
        on_update: ReferentialActionEnum | str | None = None,
    ) -> Self:
        self._alters.append(
            AddForeignKeyConstraint(
                columns=[column] if isinstance(column, str) else list(column),
                ref_table=ref_table,
                ref_columns=[ref_column] if isinstance(ref_column, str) else list(ref_column),
                name=name,
                on_delete=on_delete,
                on_update=on_update,
            )
        )
        return self

    def drop_constraint(self, constraint: str) -> Self:
        self._alters.append(DropConstraint(name=constraint))
        return self

    def alter(self, sql: str) -> Self:
        self._alters.append(RawAlter(sql=sql))
        return self

    def add_auto_increment(self, name: str, size: int = 64, add_primary_key: bool = True) -> Self:
        return self.add_identity(name, size, add_primary_key)

    def add_identity(self, name: str, size: int = 64, add_primary_key: bool = True) -> Self:
        if add_primary_key:
            self.add_primary_keys(name)
        return self.add_int(name, size, True, None, True)

    def add_bool(self, name: str, not_null: bool = False, default: bool | None = None) -> Self:
        return self.add_column(name, TypeEnum.BOOL, not_null, default)

    def add_int(
        self,
        name: str,
        size: int = 64,
        not_null: bool = False,
        default: int | None = None,
        generated_by_default_as_identity: bool = False,
    ) -> Self:
        return self.add_column(name, TypeEnum.INT, not_null, default, generated_by_default_as_identity, size=size)

    def add_float(
        self,
        name: str,
        size: int = 64,
        not_null: bool = False,
        default: float | None = None,
    ) -> Self:
        return self.add_column(name, TypeEnum.FLOAT, not_null, default, size=size)

    def add_string(
        self,
        name: str,
        size: int = 255,
        not_null: bool = False,
        default: str | None = None,
    ) -> Self:
        return self.add_column(name, TypeEnum.STRING, not_null, default, size=size)

    def add_text(self, name: str, not_null: bool = False, default: str | None = None) -> Self:
        return self.add_string(name, sys.maxsize, not_null, default)

    def add_datetime(
        self,
        name: str,
        size: int = 6,
        not_null: bool = False,
        default: Any = None,
    ) -> Self:
        return self.add_column(name, TypeEnum.DATETIME, not_null, default, size=size)

    def add_current_timestamp(
        self,
        name: str,
        size: int = 6,
        not_null: bool = False,
    ) -> Self:
        return self.add_datetime(name, size, not_null, CurrentTimestamp())
