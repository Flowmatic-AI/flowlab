from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pytest

from flowlab.modules.db import AdapterError
from flowlab.modules.db.database import DB


def _run_in_thread(callback: Any) -> Any:
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(callback).result()


class _LiveWorker:
    """A second thread that opens a connection and stays alive for the block.

    Connections are reclaimed the instant their thread exits, so any assertion
    about *two* threads holding connections has to be made while the second one
    is still running."""

    def __init__(self, db: DB) -> None:
        self._db = db
        self._ready = threading.Event()
        self._release = threading.Event()
        self._thread = threading.Thread(target=self._run, name="live-worker")
        self.connection: Any = None

    def _run(self) -> None:
        self.connection = self._db.get_connection()
        self._ready.set()
        self._release.wait(timeout=10)

    def __enter__(self) -> Self:
        self._thread.start()
        assert self._ready.wait(timeout=10)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._release.set()
        self._thread.join(timeout=10)


def _file_db(tmp_path: Path, name: str = "threads.sqlite") -> DB:
    db = DB.connect_sqlite(str(tmp_path / name), options={"journal_mode": "WAL"})
    db.exec("CREATE TABLE t (val INTEGER)")
    return db


def test_each_thread_gets_its_own_connection(tmp_path: Path) -> None:
    db = _file_db(tmp_path)
    assert db.adapter.connection_count() == 1

    main_connection = db.get_connection()

    with _LiveWorker(db) as worker:
        assert worker.connection is not main_connection
        assert db.adapter.connection_count() == 2

    db.close()


def test_a_thread_reuses_its_own_connection(tmp_path: Path) -> None:
    db = _file_db(tmp_path)

    def _twice() -> tuple[bool, int]:
        return db.get_connection() is db.get_connection(), db.adapter.connection_count()

    reused, count_while_alive = _run_in_thread(_twice)

    assert reused is True
    assert count_while_alive == 2

    db.close()


def test_writes_from_worker_threads_all_land(tmp_path: Path) -> None:
    db = _file_db(tmp_path)

    def _insert(value: int) -> None:
        db.insert("t").values({"val": value}).execute()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_insert, range(100)))

    rows = db.select("t").execute().fetch_dicts()
    assert sorted(row["val"] for row in rows) == list(range(100))

    db.close()


def test_transaction_state_does_not_leak_between_threads(tmp_path: Path) -> None:
    db = _file_db(tmp_path)

    opened = threading.Event()
    inserted = threading.Event()
    seen_in_transaction: list[bool] = []

    def _holder() -> None:
        db.begin_transaction()
        seen_in_transaction.append(db.in_transaction)
        opened.set()
        inserted.wait(timeout=5)
        db.rollback_transaction()

    holder = threading.Thread(target=_holder)
    holder.start()
    opened.wait(timeout=5)

    assert seen_in_transaction == [True]
    assert db.in_transaction is False

    db.insert("t").values({"val": 1}).execute()
    inserted.set()
    holder.join()

    rows = db.select("t").execute().fetch_dicts()
    assert [row["val"] for row in rows] == [1]

    db.close()


def test_savepoint_stacks_are_per_thread(tmp_path: Path) -> None:
    db = _file_db(tmp_path)

    db.begin_transaction()
    db.begin_transaction("sp1")
    assert db._savepoints == ["sp1"]

    assert _run_in_thread(lambda: list(db._savepoints)) == []

    db.rollback_transaction()
    db.rollback_transaction()
    db.close()


def test_reconnect_leaves_other_threads_alone(tmp_path: Path) -> None:
    db = _file_db(tmp_path)

    main_connection = db.get_connection()

    with _LiveWorker(db):
        db.reconnect()

        assert db.get_connection() is not main_connection
        assert db.adapter.connection_count() == 2

    db.close()


def test_close_closes_every_threads_connection(tmp_path: Path) -> None:
    db = DB.connect_sqlite(str(tmp_path / "closed.sqlite"), options={"check_same_thread": False})

    with _LiveWorker(db) as worker:
        worker_connection = worker.connection
        assert db.adapter.connection_count() == 2

        db.close()

        assert db.adapter.connection_count() == 0

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        worker_connection.execute("SELECT 1")


def test_queries_after_close_raise_instead_of_reconnecting(tmp_path: Path) -> None:
    db = _file_db(tmp_path)
    db.close()

    with pytest.raises(AdapterError):
        db.select("t").execute()

    with pytest.raises(AdapterError):
        _run_in_thread(lambda: db.select("t").execute())


def test_reconnect_revives_a_closed_adapter(tmp_path: Path) -> None:
    db = _file_db(tmp_path)
    db.close()

    db.reconnect()

    assert db.select("t").execute().fetch_dicts() == []
    db.close()


def test_a_finished_threads_connection_is_closed_at_thread_exit(tmp_path: Path) -> None:
    db = DB.connect_sqlite(str(tmp_path / "reclaimed.sqlite"), options={"check_same_thread": False})

    worker_connection = _run_in_thread(db.get_connection)

    # Reclaimed by the thread itself on the way out -- no later caller has to
    # come along and notice, and nothing polls for it.
    assert db.adapter.connection_count() == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        worker_connection.execute("SELECT 1")

    db.close()


def test_thread_churn_does_not_accumulate_connections(tmp_path: Path) -> None:
    db = _file_db(tmp_path)

    for _ in range(25):
        _run_in_thread(lambda: db.insert("t").values({"val": 1}).execute())
        assert db.adapter.connection_count() == 1

    assert db.select("t").execute().fetch_dicts() != []

    db.close()


def test_thread_churn_does_not_accumulate_savepoint_stacks(tmp_path: Path) -> None:
    db = _file_db(tmp_path)

    assert db._savepoints == []

    for _ in range(25):
        _run_in_thread(lambda: db._savepoints)

    # Only this thread's stack is left; the 25 finished ones went with them.
    assert db._savepoint_stacks.count() == 1

    db.close()


def test_persistent_close_keeps_every_threads_connection(tmp_path: Path) -> None:
    db = DB.connect_sqlite(str(tmp_path / "persistent.sqlite"), options={"persistent": True})
    db.exec("CREATE TABLE t (val INTEGER)")

    with _LiveWorker(db):
        db.close()

        assert db.adapter.connection_count() == 2

    # `persistent` spares the handles close() would otherwise drop, but a
    # finished thread's connection is unreachable -- no thread can ever bind to
    # it again -- so it is reclaimed regardless.
    assert db.adapter.connection_count() == 1
    assert db.select("t").execute().fetch_dicts() == []


def test_memory_database_is_shared_between_threads() -> None:
    db = DB.connect_sqlite(":memory:")
    db.exec("CREATE TABLE t (val INTEGER)")

    _run_in_thread(lambda: db.insert("t").values({"val": 7}).execute())

    rows = db.select("t").execute().fetch_dicts()
    assert [row["val"] for row in rows] == [7]
    assert db.adapter.connection_count() == 1

    db.close()


def test_memory_database_survives_concurrent_writers() -> None:
    db = DB.connect_sqlite(":memory:")
    db.exec("CREATE TABLE t (val INTEGER)")

    def _insert(value: int) -> None:
        db.insert("t").values({"val": value}).execute()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_insert, range(100)))

    rows = db.select("t").execute().fetch_dicts()
    assert sorted(row["val"] for row in rows) == list(range(100))

    db.close()


def test_sharing_one_handle_between_threads_is_refused_by_default(tmp_path: Path) -> None:
    db = _file_db(tmp_path)
    connection = db.get_connection()

    with pytest.raises(sqlite3.ProgrammingError, match="same thread"):
        _run_in_thread(lambda: connection.execute("SELECT 1"))

    db.close()


def test_check_same_thread_option_can_opt_out(tmp_path: Path) -> None:
    db = DB.connect_sqlite(str(tmp_path / "opt_out.sqlite"), options={"check_same_thread": False})
    connection = db.get_connection()

    assert _run_in_thread(lambda: connection.execute("SELECT 1").fetchone()[0]) == 1

    db.close()


def test_memory_database_keeps_the_check_off_for_its_shared_handle() -> None:
    db = DB.connect_sqlite(":memory:")
    connection = db.get_connection()

    assert _run_in_thread(lambda: connection.execute("SELECT 1").fetchone()[0]) == 1

    db.close()
