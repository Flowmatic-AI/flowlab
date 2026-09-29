from __future__ import annotations

from flowlab.modules.db.result import Result, snapshot_result


def test_result_creation() -> None:
    result: Result = Result(columns={"id": "INTEGER", "name": "TEXT"})
    assert result.columns() == {"id": "INTEGER", "name": "TEXT"}
    assert result.fetch_dict() is None
    assert result.fetch_dicts() == []


def test_result_fetch_dict() -> None:
    result: Result = Result(
        columns={"id": "INTEGER", "name": "TEXT"},
        rows=[{"id": 1, "name": "John"}, {"id": 2, "name": "Jane"}],
    )
    row: dict | None = result.fetch_dict()
    assert row == {"id": 1, "name": "John"}
    row2: dict | None = result.fetch_dict()
    assert row2 == {"id": 2, "name": "Jane"}
    assert result.fetch_dict() is None


def test_result_fetch_dicts() -> None:
    result: Result = Result(
        columns={"id": "INTEGER", "name": "TEXT"},
        rows=[{"id": 1, "name": "John"}, {"id": 2, "name": "Jane"}],
    )
    rows: list[dict] = result.fetch_dicts()
    assert len(rows) == 2
    assert rows[0]["name"] == "John"


def test_result_scalar() -> None:
    result: Result = Result(
        columns={"cnt": "INTEGER"},
        rows=[{"cnt": 42}],
    )
    val: int | None = result.scalar()
    assert val == 42


def test_result_scalar_named() -> None:
    result: Result = Result(
        columns={"cnt": "INTEGER"},
        rows=[{"cnt": 42}],
    )
    val: int | None = result.scalar("cnt")
    assert val == 42


def test_result_scalar_empty() -> None:
    result: Result = Result(columns={"cnt": "INTEGER"})
    assert result.scalar() is None


def test_result_fetch_object() -> None:
    result: Result = Result(
        columns={"id": "INTEGER", "name": "TEXT"},
        rows=[{"id": 1, "name": "John"}],
    )
    obj: object | dict | None = result.fetch_object()
    assert obj == {"id": 1, "name": "John"}


def test_result_fetch_objects() -> None:
    result: Result = Result(
        columns={"id": "INTEGER", "name": "TEXT"},
        rows=[{"id": 1, "name": "John"}, {"id": 2, "name": "Jane"}],
    )
    objs: list[dict] = result.fetch_objects()
    assert len(objs) == 2


def test_result_from_result() -> None:
    inner: Result = Result(
        columns={"id": "INTEGER"},
        rows=[{"id": 1}, {"id": 2}],
    )
    snapshot: Result = snapshot_result(inner)
    assert snapshot.columns() == {"id": "INTEGER"}
    rows: list[dict] = snapshot.fetch_dicts()
    assert len(rows) == 2
    assert inner.fetch_dicts() == []
