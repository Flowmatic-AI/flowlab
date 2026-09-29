from __future__ import annotations

from typing import Any

from flowlab.modules.db.query import SelectQuery
from flowlab.modules.db.query.expressions import Alias, CurrentTimestamp, Expression, Identifier, Raw, SubQuery


def escape_ansi(string: str, chars: str) -> str:
    escaped = string
    for char in chars:
        escaped = escaped.replace(char, char * 2)
    return escaped


def escape_backslash(string: str, chars: str) -> str:
    escaped = string
    for char in "\\" + chars:
        escaped = escaped.replace(char, "\\" + char)
    return escaped


def raw(sql: str) -> Raw:
    return Raw(sql)


def identifier(identifier: str | list[Any]) -> Identifier:
    return Identifier(identifier)


def alias(identifier: str | list[str] | Any, alias: str) -> Alias:
    return Alias(identifier, alias)


def expression(sql: str, params: list[Any] | None = None) -> Expression:
    return Expression(sql, params)


def sub_query(query: SelectQuery, alias: str) -> SubQuery:
    return SubQuery(query, alias)


def current_timestamp() -> CurrentTimestamp:
    return CurrentTimestamp()


def now() -> CurrentTimestamp:
    return current_timestamp()
