from __future__ import annotations

from typing import Any

from flowlab.modules.db.result._base import ResultABC


def snapshot_result(result: ResultABC) -> Result:
    columns = result.columns()
    rows = result.fetch_dicts()
    return Result(columns=columns, rows=rows)


class Result(ResultABC):
    def __init__(self, columns: dict[str, str], rows: list[dict[str, Any]] | None = None) -> None:
        self._columns = dict(columns)
        self._rows = list(rows) if rows else []

    def columns(self) -> dict[str, str]:
        return dict(self._columns)

    def fetch_dict(self) -> dict[str, Any] | None:
        if not self._rows:
            return None
        return self._rows.pop(0)

    def fetch_dicts(self) -> list[dict[str, Any]]:
        result = list(self._rows)
        self._rows.clear()
        return result
