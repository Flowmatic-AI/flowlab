from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


def _row_to_object(row: dict[str, Any], target_class: type, constructor_args: list[Any]) -> object | dict[str, Any]:
    if target_class is dict or target_class is None:
        return dict(row)
    obj: object = target_class(*constructor_args)
    obj.__dict__.update(row)
    return obj


class ResultABC(ABC):
    @abstractmethod
    def columns(self) -> dict[str, str]: ...

    def scalar(self, column: str | None = None) -> Any:
        row = self.fetch_dict()
        if row is None:
            return None
        if column is not None:
            return row.get(column)
        return next(iter(row.values()), None)

    def scalars(self, column: str | None = None) -> list[Any]:
        rows = self.fetch_dicts()
        if column is not None:
            return [row.get(column) for row in rows]
        return [next(iter(row.values()), None) for row in rows]

    def fetch_object(
        self, target_class: type = dict, constructor_args: list[Any] | None = None
    ) -> object | dict[str, Any] | None:
        row = self.fetch_dict()
        if row is None:
            return None
        return _row_to_object(row, target_class, constructor_args or [])

    def fetch_objects(
        self, target_class: type = dict, constructor_args: list[Any] | None = None
    ) -> list[object | dict[str, Any]]:
        return [_row_to_object(row, target_class, constructor_args or []) for row in self.fetch_dicts()]

    @abstractmethod
    def fetch_dict(self) -> dict[str, Any] | None: ...

    @abstractmethod
    def fetch_dicts(self) -> list[dict[str, Any]]: ...
