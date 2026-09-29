from __future__ import annotations

import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pytest

from flowlab.modules.db import DB, AdapterError, ConnectionLimitError


class _Holders:
    """N threads that each take a connection and hold it for the block.

    A slot only comes free when the thread holding it exits, so every assertion
    about a *full* pool has to be made while its holders are still running."""

    def __init__(self, db: DB, count: int) -> None:
        self._db = db
        self._ready = threading.Barrier(count + 1, timeout=10)
        self._release = threading.Event()
        self._threads = [threading.Thread(target=self._run, name=f"holder-{index}") for index in range(count)]
        self._lock = threading.Lock()
        self.connections: list[Any] = []

    def _run(self) -> None:
        connection = self._db.get_connection()
        with self._lock:
            self.connections.append(connection)
        self._ready.wait()
        self._release.wait(timeout=10)

    def __enter__(self) -> Self:
        for thread in self._threads:
            thread.start()
        self._ready.wait()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._release.set()
        for thread in self._threads:
            thread.join(timeout=10)


class _Waiter:
    """A thread that queues for a connection and exits the moment it gets one.

    Exiting is the whole point: a pooled worker would keep the slot it was
    handed, so the next thread in line would never see it come free. That also
    rules out :class:`ThreadPoolExecutor` for anything expected to block --
    its shutdown joins workers that are still waiting on a slot the test has
    not released yet."""

    def __init__(self, db: DB, index: int = 0, order: list[int] | None = None) -> None:
        self._db = db
        self._index = index
        self._order = order
        self._thread = threading.Thread(target=self._run, name=f"waiter-{index}")
        self.acquired = threading.Event()
        self.error: AdapterError | sqlite3.Error | None = None

    def _run(self) -> None:
        try:
            self._db.get_connection()
        except (AdapterError, sqlite3.Error) as exc:
            self.error = exc
            return

        if self._order is not None:
            self._order.append(self._index)

        self.acquired.set()

    def start(self) -> None:
        self._thread.start()

    def join(self) -> None:
        self._thread.join(timeout=10)


def _limited_db(tmp_path: Path, max_concurrent_connections: int, acquire_connection_timeout: float | None = None) -> DB:
    db = DB.connect_sqlite(
        str(tmp_path / "limited.sqlite"),
        options={"check_same_thread": False},
        max_concurrent_connections=max_concurrent_connections,
        acquire_connection_timeout=acquire_connection_timeout,
    )
    db.exec("CREATE TABLE IF NOT EXISTS t (val INTEGER)")
    return db


def test_unlimited_by_default(tmp_path: Path) -> None:
    db = DB.connect_sqlite(str(tmp_path / "unlimited.sqlite"))

    assert db.adapter.max_concurrent_connections is None
    assert db.adapter.acquire_connection_timeout is None

    with _Holders(db, 6):
        assert db.adapter.connection_count() == 7

    db.close()


def test_max_concurrent_connections_caps_live_connections(tmp_path: Path) -> None:
    # One slot goes to this thread, leaving two for the holders.
    db = _limited_db(tmp_path, max_concurrent_connections=3)

    waiter = _Waiter(db)

    with _Holders(db, 2):
        assert db.adapter.connection_count() == 3

        # The pool is full, so the fourth thread has nowhere to go.
        waiter.start()
        assert not waiter.acquired.wait(timeout=0.5)
        assert db.adapter.connection_count() == 3

    # A holder exited, so the waiter got its slot.
    assert waiter.acquired.wait(timeout=10)
    assert waiter.error is None
    waiter.join()

    db.close()


def test_a_freed_slot_goes_to_the_next_thread_in_line(tmp_path: Path) -> None:
    db = _limited_db(tmp_path, max_concurrent_connections=2)
    order: list[int] = []
    waiters = [_Waiter(db, index, order) for index in range(4)]

    with _Holders(db, 1):
        assert db.adapter.connection_count() == 2

        for waiter in waiters:
            waiter.start()
            # Arrival order decides service order, so let each one reach the
            # queue before the next is started.
            waiter.acquired.wait(timeout=0.05)

        assert order == []

    for waiter in waiters:
        assert waiter.acquired.wait(timeout=10)
        waiter.join()

    # The single freed slot passed down the queue in arrival order, each thread
    # handing it on as it exited.
    assert order == [0, 1, 2, 3]

    db.close()


def test_never_more_than_the_limit_under_churn(tmp_path: Path) -> None:
    db = _limited_db(tmp_path, max_concurrent_connections=4, acquire_connection_timeout=30.0)
    peak = 0
    peak_lock = threading.Lock()
    errors: list[AdapterError | sqlite3.Error] = []

    # Ten short-lived threads against four slots -- one of which this thread
    # already holds. Most of them have to queue, and each hands its slot on by
    # exiting, so the run only finishes if slots really are recycled.
    def _work(start: int) -> None:
        nonlocal peak
        try:
            for value in range(start, start + 20):
                db.insert("t").values({"val": value}).execute()
                with peak_lock:
                    peak = max(peak, db.adapter.connection_count())
        except (AdapterError, sqlite3.Error) as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_work, args=(index * 20,)) for index in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive()

    assert errors == []
    assert peak == 4

    rows = db.select("t").execute().fetch_dicts()
    assert sorted(row["val"] for row in rows) == list(range(200))

    db.close()


def test_acquire_connection_timeout_raises_instead_of_waiting_forever(tmp_path: Path) -> None:
    db = _limited_db(tmp_path, max_concurrent_connections=2, acquire_connection_timeout=0.2)

    with _Holders(db, 1):
        waiter = _Waiter(db)
        waiter.start()
        waiter.join()

    assert isinstance(waiter.error, ConnectionLimitError)
    assert "no connection slot came free" in str(waiter.error)

    db.close()


def test_connection_limit_error_is_an_adapter_error(tmp_path: Path) -> None:
    db = _limited_db(tmp_path, max_concurrent_connections=1, acquire_connection_timeout=0.1)

    waiter = _Waiter(db)
    waiter.start()
    waiter.join()

    assert isinstance(waiter.error, AdapterError)

    db.close()


def test_a_thread_that_already_holds_one_never_queues(tmp_path: Path) -> None:
    db = _limited_db(tmp_path, max_concurrent_connections=1, acquire_connection_timeout=0.1)

    # The pool is full -- with this thread's own connection. Reusing it must not
    # go anywhere near the queue, or every capped adapter would deadlock itself.
    assert db.get_connection() is db.get_connection()
    assert db.select("t").execute().fetch_dicts() == []

    db.close()


def test_a_timed_out_wait_does_not_burn_the_slot(tmp_path: Path) -> None:
    db = _limited_db(tmp_path, max_concurrent_connections=2, acquire_connection_timeout=0.2)

    with _Holders(db, 1):
        for _ in range(3):
            waiter = _Waiter(db)
            waiter.start()
            waiter.join()
            assert isinstance(waiter.error, ConnectionLimitError)

    # The three failures handed back what they took, and the holder's slot came
    # back when it exited, so both are free again.
    with _Holders(db, 1):
        assert db.adapter.connection_count() == 2

    db.close()


def test_a_failed_open_releases_its_slot(tmp_path: Path) -> None:
    directory = tmp_path / "vanishing"
    directory.mkdir()

    db = _limited_db(directory, max_concurrent_connections=2, acquire_connection_timeout=0.2)

    # The open handle survives, but there is nowhere for a new one to be created.
    shutil.rmtree(directory)

    for _ in range(3):
        waiter = _Waiter(db)
        waiter.start()
        waiter.join()
        assert isinstance(waiter.error, sqlite3.OperationalError)

    directory.mkdir()

    with _Holders(db, 1):
        assert db.adapter.connection_count() == 2

    db.close()


def test_close_frees_every_slot(tmp_path: Path) -> None:
    db = _limited_db(tmp_path, max_concurrent_connections=2)

    with _Holders(db, 1):
        assert db.adapter.connection_count() == 2
        db.close()
        assert db.adapter.connection_count() == 0

    db.reconnect()

    with _Holders(db, 1):
        assert db.adapter.connection_count() == 2

    db.close()


def test_reconnect_hands_its_slot_back_before_taking_a_new_one(tmp_path: Path) -> None:
    db = _limited_db(tmp_path, max_concurrent_connections=1, acquire_connection_timeout=0.5)

    # The single slot is this thread's. reconnect() drops the handle first, so
    # the re-open finds it free rather than waiting on itself.
    db.reconnect()

    assert db.select("t").execute().fetch_dicts() == []
    assert db.adapter.connection_count() == 1

    db.close()


def test_thread_churn_does_not_leak_slots(tmp_path: Path) -> None:
    db = _limited_db(tmp_path, max_concurrent_connections=2, acquire_connection_timeout=1.0)

    for _ in range(50):
        waiter = _Waiter(db)
        waiter.start()
        waiter.join()
        assert waiter.error is None

    # 50 threads came and went through a 2-slot pool without exhausting it.
    with _Holders(db, 1):
        assert db.adapter.connection_count() == 2

    db.close()


def test_max_concurrent_connections_below_one_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="max_concurrent_connections must be at least 1"):
        DB.connect_sqlite(str(tmp_path / "invalid.sqlite"), max_concurrent_connections=0)


def test_memory_database_holds_one_slot_for_its_shared_handle() -> None:
    db = DB.connect_sqlite(":memory:", max_concurrent_connections=1, acquire_connection_timeout=0.5)
    db.exec("CREATE TABLE t (val INTEGER)")

    # Every thread shares the one handle, so the cap is never approached.
    def _insert(value: int) -> None:
        db.insert("t").values({"val": value}).execute()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_insert, range(50)))

    rows = db.select("t").execute().fetch_dicts()
    assert sorted(row["val"] for row in rows) == list(range(50))
    assert db.adapter.connection_count() == 1

    db.close()
