from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, TypeVar


@dataclass(frozen=True)
class ColumnInfo:
    column_name: str | None = None
    primary_key: bool = False
    auto_increment: bool = False


def column(column_name: str | None = None, primary_key: bool = False, auto_increment: bool = False) -> ColumnInfo:
    return ColumnInfo(column_name=column_name, primary_key=primary_key, auto_increment=auto_increment)


@dataclass(frozen=True)
class ModelColumn:
    field_name: str
    column_name: str
    primary_key: bool
    auto_increment: bool


ColumnT = TypeVar("ColumnT")

PrimaryKey = Annotated[ColumnT, ColumnInfo(primary_key=True)]

AutoIncrement = Annotated[int | None, ColumnInfo(primary_key=True, auto_increment=True)]
