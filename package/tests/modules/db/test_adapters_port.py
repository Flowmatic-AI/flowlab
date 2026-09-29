"""Regression tests for hand-port bugs found in the adapters/result layer.

These focus on behavior that can be verified without a live MySQL/Postgres
server: the SQLite adapter (embedded, no server needed) exercises most of
the shared AdapterABC bookkeeping directly, while a couple of tests use
lightweight fakes to pin down MySQL/Postgres-specific fixes.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from flowlab.modules.db._threading import ThreadLocalStore
from flowlab.modules.db.adapters import AdapterABC, SQLiteAdapter
from flowlab.modules.db.database import DB, DatabaseABC
from flowlab.modules.db.dialects import MySQLDialect, PostgresqlDialect, SQLiteDialect
from flowlab.modules.db.result import Result, ResultABC


def _bind_fake_connection(adapter: Any, connection: Any) -> None:
    store: ThreadLocalStore[Any] = ThreadLocalStore()
    store.set(connection)
    adapter._connections = store
    adapter._closed = False


def test_sqlite_adapter_has_close() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    adapter.close()


def test_sqlite_adapter_close_runs_optimize_when_requested() -> None:
    adapter = SQLiteAdapter(database_name=":memory:", options={"optimize": True})
    adapter.close()


def test_commit_transaction_without_active_transaction_is_noop() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    assert adapter.in_transaction is False
    adapter.commit_transaction("COMMIT TRANSACTION")
    adapter.rollback_transaction("ROLLBACK TRANSACTION")


def test_begin_transaction_twice_is_noop() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    adapter.begin_transaction("BEGIN TRANSACTION")
    assert adapter.in_transaction is True
    adapter.begin_transaction("BEGIN TRANSACTION")
    assert adapter.in_transaction is True
    adapter.rollback_transaction("ROLLBACK TRANSACTION")


def test_savepoint_without_active_transaction_is_noop() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    assert adapter.in_transaction is False
    adapter.begin_savepoint('SAVEPOINT "sp1"')
    adapter.commit_savepoint('RELEASE SAVEPOINT "sp1"')
    adapter.rollback_savepoint('ROLLBACK TO SAVEPOINT "sp1"')


def test_savepoint_rollback_discards_only_inner_work() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    dialect = SQLiteDialect()
    adapter.exec("CREATE TABLE t (val INTEGER)")
    adapter.commit_transaction(dialect.commit_transaction().query)

    adapter.begin_transaction(dialect.begin_transaction().query)
    adapter.query("INSERT INTO t VALUES (1)")
    adapter.begin_savepoint(dialect.begin_savepoint("sp1").query)
    adapter.query("INSERT INTO t VALUES (2)")
    adapter.rollback_savepoint(dialect.rollback_savepoint("sp1").query)
    adapter.commit_transaction(dialect.commit_transaction().query)

    rows = adapter.query("SELECT val FROM t").fetch_dicts()
    assert [r["val"] for r in rows] == [1]
    adapter.close()


def test_sqlite_savepoint_name_requiring_escaping_works_end_to_end() -> None:
    """A savepoint name that is not a bare valid SQL identifier (contains a
    space) only works if the dialect's escaped identifier reaches the
    adapter -- the old adapter-level `f"SAVEPOINT {name}"` string would emit
    invalid SQL for a name like this."""
    adapter = SQLiteAdapter(database_name=":memory:")
    dialect = SQLiteDialect()
    db = DatabaseABC(adapter, dialect)

    db.exec("CREATE TABLE t (val INTEGER)")
    db.commit_transaction()

    db.begin_transaction()
    db.exec("INSERT INTO t VALUES (1)")
    db.begin_transaction("my savepoint")
    db.exec("INSERT INTO t VALUES (2)")
    db.rollback_transaction()
    db.commit_transaction()

    rows = db.query("SELECT val FROM t").fetch_dicts()
    assert [r["val"] for r in rows] == [1]
    adapter.close()


def test_sqlite_query_builder_writes_are_durable_after_close(tmp_path: Path) -> None:
    """Regression test for a hand-port bug: connecting with the stdlib
    default `isolation_level=""` leaves an implicit transaction open after
    DML executed through query_with_params() (the query-builder path),
    which exec()'s commit() never covers. Against a real file (unlike
    `:memory:`, which cannot tell the difference), the row is silently
    discarded on close. Connecting with `isolation_level=None`
    (autocommit) fixes this."""
    db_path = str(tmp_path / "durable.db")

    adapter = SQLiteAdapter(database_name=db_path)
    dialect = SQLiteDialect()
    db = DatabaseABC(adapter, dialect)
    db.exec("CREATE TABLE t (val INTEGER)")
    db.insert("t").values({"val": 1}).execute()
    adapter.close()

    reopened = SQLiteAdapter(database_name=db_path)
    rows = reopened.query("SELECT val FROM t").fetch_dicts()
    assert [r["val"] for r in rows] == [1]
    reopened.close()


def test_sqlite_committed_transaction_is_durable_after_close(tmp_path: Path) -> None:
    db_path = str(tmp_path / "durable_commit.db")

    adapter = SQLiteAdapter(database_name=db_path)
    dialect = SQLiteDialect()
    db = DatabaseABC(adapter, dialect)
    db.exec("CREATE TABLE t (val INTEGER)")

    db.begin_transaction()
    db.insert("t").values({"val": 1}).execute()
    db.commit_transaction()
    adapter.close()

    reopened = SQLiteAdapter(database_name=db_path)
    rows = reopened.query("SELECT val FROM t").fetch_dicts()
    assert [r["val"] for r in rows] == [1]
    reopened.close()


def test_sqlite_rolled_back_transaction_is_absent_after_close(tmp_path: Path) -> None:
    db_path = str(tmp_path / "durable_rollback.db")

    adapter = SQLiteAdapter(database_name=db_path)
    dialect = SQLiteDialect()
    db = DatabaseABC(adapter, dialect)
    db.exec("CREATE TABLE t (val INTEGER)")

    db.begin_transaction()
    db.insert("t").values({"val": 1}).execute()
    db.rollback_transaction()
    adapter.close()

    reopened = SQLiteAdapter(database_name=db_path)
    rows = reopened.query("SELECT val FROM t").fetch_dicts()
    assert rows == []
    reopened.close()


def test_sqlite_nested_savepoints_are_durable_after_close(tmp_path: Path) -> None:
    """begin -> begin (savepoint) -> commit (release savepoint) -> commit
    (commit transaction), against a real file, closing and reopening to
    confirm the kept row actually persisted to disk."""
    db_path = str(tmp_path / "durable_savepoint_commit.db")

    adapter = SQLiteAdapter(database_name=db_path)
    dialect = SQLiteDialect()
    db = DatabaseABC(adapter, dialect)
    db.exec("CREATE TABLE t (val INTEGER)")

    db.begin_transaction()
    db.insert("t").values({"val": 1}).execute()

    db.begin_transaction()
    db.insert("t").values({"val": 2}).execute()
    db.commit_transaction()

    db.commit_transaction()
    adapter.close()

    reopened = SQLiteAdapter(database_name=db_path)
    rows = reopened.query("SELECT val FROM t").fetch_dicts()
    assert sorted(r["val"] for r in rows) == [1, 2]
    reopened.close()


def test_sqlite_nested_savepoint_rollback_is_absent_after_close(tmp_path: Path) -> None:
    """begin -> begin (savepoint) -> rollback (rollback to savepoint) ->
    commit (commit transaction), against a real file: only the outer row
    survives close/reopen."""
    db_path = str(tmp_path / "durable_savepoint_rollback.db")

    adapter = SQLiteAdapter(database_name=db_path)
    dialect = SQLiteDialect()
    db = DatabaseABC(adapter, dialect)
    db.exec("CREATE TABLE t (val INTEGER)")

    db.begin_transaction()
    db.insert("t").values({"val": 1}).execute()

    db.begin_transaction()
    db.insert("t").values({"val": 2}).execute()
    db.rollback_transaction()

    db.commit_transaction()
    adapter.close()

    reopened = SQLiteAdapter(database_name=db_path)
    rows = reopened.query("SELECT val FROM t").fetch_dicts()
    assert [r["val"] for r in rows] == [1]
    reopened.close()


class _RecordingAdapter(AdapterABC):
    def __init__(self) -> None:
        super().__init__(driver_name="fake", database_name="fake")
        self._in_transaction = False
        self._connected = True
        self.statements: list[str] = []
        self.connects = 0

    def _connect(self) -> None:
        self._connected = True
        self.connects += 1

    def _disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def version(self) -> str:
        return "0"

    def exec(self, query: str) -> None:
        self.statements.append(query)
        if query.startswith(("BEGIN", "START TRANSACTION")):
            self._in_transaction = True
        elif query in ("COMMIT TRANSACTION", "COMMIT", "ROLLBACK TRANSACTION", "ROLLBACK"):
            self._in_transaction = False

    def query(self, query: str) -> ResultABC:
        raise NotImplementedError

    def query_with_params(
        self,
        dialect: Any,
        query_with_params: Any,
        emulate_prepare: bool = False,
    ) -> ResultABC:
        raise NotImplementedError

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    def last_insert_id(self, name: str | None = None) -> int | str | None:
        return None

    def get_connection(self) -> Any:
        return None

    def close(self) -> None:
        self._disconnect()


def test_database_sends_sqlite_dialect_sql_to_adapter_for_transactions_and_savepoints() -> None:
    adapter = _RecordingAdapter()
    dialect = SQLiteDialect()
    db = DatabaseABC(adapter, dialect)

    db.begin_transaction()
    assert adapter.statements == ["BEGIN TRANSACTION"]

    db.begin_transaction('sp"1')
    assert adapter.statements[-1] == 'SAVEPOINT "sp""1"'

    db.commit_transaction()
    assert adapter.statements[-1] == 'RELEASE SAVEPOINT "sp""1"'

    db.commit_transaction()
    assert adapter.statements[-1] == "COMMIT TRANSACTION"


def test_database_sends_mysql_dialect_sql_to_adapter_for_transactions_and_savepoints() -> None:
    adapter = _RecordingAdapter()
    dialect = MySQLDialect()
    db = DatabaseABC(adapter, dialect)

    db.begin_transaction()
    assert adapter.statements == ["START TRANSACTION"]

    db.begin_transaction("sp1")
    assert adapter.statements[-1] == "SAVEPOINT `sp1`"

    db.rollback_transaction()
    assert adapter.statements[-1] == "ROLLBACK TO SAVEPOINT `sp1`"

    db.commit_transaction()
    assert adapter.statements[-1] == "COMMIT"


def test_database_sends_postgres_dialect_sql_to_adapter_for_transactions_and_savepoints() -> None:
    adapter = _RecordingAdapter()
    dialect = PostgresqlDialect()
    db = DatabaseABC(adapter, dialect)

    db.begin_transaction()
    assert adapter.statements == ["BEGIN TRANSACTION"]

    db.begin_transaction("sp1")
    assert adapter.statements[-1] == 'SAVEPOINT "sp1"'

    db.commit_transaction()
    assert adapter.statements[-1] == 'RELEASE SAVEPOINT "sp1"'

    db.rollback_transaction()
    assert adapter.statements[-1] == "ROLLBACK TRANSACTION"


def test_sqlite_foreign_keys_pragma_on_by_default() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    row = adapter.query("PRAGMA foreign_keys").fetch_dict()
    assert row is not None
    assert row["foreign_keys"] == 1
    adapter.close()


def test_sqlite_foreign_keys_pragma_can_be_disabled() -> None:
    adapter = SQLiteAdapter(database_name=":memory:", options={"foreign_keys": False})
    row = adapter.query("PRAGMA foreign_keys").fetch_dict()
    assert row is not None
    assert row["foreign_keys"] == 0
    adapter.close()


def test_sqlite_foreign_keys_pragma_applied_when_requested() -> None:
    adapter = SQLiteAdapter(database_name=":memory:", options={"foreign_keys": True})
    row = adapter.query("PRAGMA foreign_keys").fetch_dict()
    assert row is not None
    assert row["foreign_keys"] == 1
    adapter.close()


def test_sqlite_journal_mode_left_alone_by_default() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    row = adapter.query("PRAGMA journal_mode").fetch_dict()
    assert row is not None
    assert row["journal_mode"] != "wal"
    adapter.close()


def test_sqlite_memory_connection_usable_from_another_thread() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    results: list[Any] = []

    def run() -> None:
        try:
            row = adapter.query("SELECT 1 AS one").fetch_dict()
            results.append(row)
        except Exception as e:  # noqa: BLE001 - the failure itself is the assertion
            results.append(e)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert results == [{"one": 1}]
    adapter.close()


def test_sqlite_memory_same_thread_check_can_be_forced_on() -> None:
    adapter = SQLiteAdapter(database_name=":memory:", options={"check_same_thread": True})
    errors: list[Exception] = []

    def run() -> None:
        try:
            adapter.query("SELECT 1")
        except Exception as e:  # noqa: BLE001 - any driver error proves the check fired
            errors.append(e)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()

    assert len(errors) == 1
    assert isinstance(errors[0], sqlite3.ProgrammingError)
    adapter.close()


def test_sqlite_regexp_like_function_registered() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    row = adapter.query("SELECT regexp_like('hello world', 'wor') AS m").fetch_dict()
    assert row is not None
    assert row["m"] == 1

    row = adapter.query("SELECT regexp_like('hello world', 'xyz') AS m").fetch_dict()
    assert row is not None
    assert row["m"] == 0
    adapter.close()


def test_sqlite_regexp_like_function_flags() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    row = adapter.query("SELECT regexp_like('HELLO', 'hello', 'i') AS m").fetch_dict()
    assert row is not None
    assert row["m"] == 1
    adapter.close()


def test_sqlite_regexp_operator_still_works() -> None:
    """REGEXP itself must keep working (pattern, value) SQLite call order."""
    adapter = SQLiteAdapter(database_name=":memory:")
    row = adapter.query("SELECT 'hello' REGEXP 'ell' AS m").fetch_dict()
    assert row is not None
    assert row["m"] == 1
    adapter.close()


def test_sqlite_create_functions_option_registers_custom_function() -> None:
    adapter = SQLiteAdapter(
        database_name=":memory:",
        options={"create_functions": {"double_it": lambda x: x * 2}},
    )
    row = adapter.query("SELECT double_it(21) AS v").fetch_dict()
    assert row is not None
    assert row["v"] == 42
    adapter.close()


def test_sqlite_result_columns_reflect_runtime_types() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    adapter.exec("CREATE TABLE t (i INTEGER, f REAL, s TEXT, b BLOB)")
    adapter.exec("INSERT INTO t VALUES (1, 1.5, 'x', X'0011')")
    result = adapter.query("SELECT * FROM t")
    row = result.fetch_dict()
    assert row == {"i": 1, "f": 1.5, "s": "x", "b": b"\x00\x11"}
    columns = result.columns()
    assert columns == {"i": "INTEGER", "f": "FLOAT", "s": "TEXT", "b": "BLOB"}
    adapter.close()


def test_result_scalars_default_column() -> None:
    result = Result(columns={"cnt": "INTEGER"}, rows=[{"cnt": 1}, {"cnt": 2}, {"cnt": 3}])
    assert result.scalars() == [1, 2, 3]


def test_result_scalars_named_column() -> None:
    result = Result(
        columns={"id": "INTEGER", "name": "TEXT"},
        rows=[{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],
    )
    assert result.scalars("name") == ["a", "b"]


def test_result_scalars_empty() -> None:
    result = Result(columns={"cnt": "INTEGER"})
    assert result.scalars() == []


class _FakeMySQLCursor:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def execute(self, query: str, params: Any = None) -> None:
        pass

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row

    def fetchall(self) -> list[Any]:
        return []


class _FakeMySQLConnection:
    """Stands in for mysql.connector.MySQLConnection: cursor()-based only,
    deliberately has no execute()/in_transaction so the test fails loudly
    if version()/in_transaction ever regress to calling them directly."""

    def __init__(self, version_row: tuple[Any, ...] | None) -> None:
        self._version_row = version_row

    def cursor(self) -> _FakeMySQLCursor:
        return _FakeMySQLCursor(self._version_row)


def test_mysql_adapter_version_uses_a_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    from flowlab.modules.db.adapters import MySQLAdapter

    adapter = MySQLAdapter.__new__(MySQLAdapter)
    _bind_fake_connection(adapter, _FakeMySQLConnection(("8.0.32",)))
    adapter._cursors = ThreadLocalStore()

    assert adapter.version() == "8.0.32"


def test_psycopg_adapter_in_transaction_reflects_real_state() -> None:
    """in_transaction is derived purely from the connection's real
    transaction_status now that begin_transaction() runs an explicit
    dialect-provided BEGIN instead of flipping autocommit -- autocommit is
    left at True (psycopg3's default) throughout and has no bearing on the
    result."""
    pytest.importorskip("psycopg")
    from psycopg.pq import TransactionStatus

    from flowlab.modules.db.adapters import PsycopgAdapter

    class _FakeInfo:
        def __init__(self, status: Any) -> None:
            self.transaction_status = status

    class _FakeConnection:
        def __init__(self, status: Any, autocommit: bool = True) -> None:
            self.info = _FakeInfo(status)
            self.autocommit = autocommit

    adapter = PsycopgAdapter.__new__(PsycopgAdapter)

    _bind_fake_connection(adapter, _FakeConnection(TransactionStatus.IDLE))
    assert adapter.in_transaction is False

    _bind_fake_connection(adapter, _FakeConnection(TransactionStatus.INTRANS))
    assert adapter.in_transaction is True

    _bind_fake_connection(adapter, _FakeConnection(TransactionStatus.IDLE, autocommit=False))
    assert adapter.in_transaction is False


def test_psycopg_begin_transaction_emits_dialect_sql() -> None:
    """Since psycopg3 in autocommit mode injects no implicit BEGIN of its
    own, the adapter must send the dialect's own BEGIN TRANSACTION statement
    to open the transaction, and must leave autocommit alone (unlike the
    old design, which flipped autocommit and relied on psycopg3's implicit
    BEGIN instead of emitting any SQL)."""
    pytest.importorskip("psycopg")
    from psycopg.pq import TransactionStatus

    from flowlab.modules.db.adapters import PsycopgAdapter

    class _FakeInfo:
        def __init__(self, status: Any) -> None:
            self.transaction_status = status
            self.encoding = "utf-8"

        def _set(self, status: Any) -> None:
            self.transaction_status = status

    class _RecordingConnection:
        def __init__(self) -> None:
            self.info = _FakeInfo(TransactionStatus.IDLE)
            self.autocommit = True
            self.statements: list[str] = []

        def execute(self, query: bytes) -> None:
            decoded = query.decode("utf-8")
            self.statements.append(decoded)
            if decoded == "BEGIN TRANSACTION":
                self.info._set(TransactionStatus.INTRANS)
            elif decoded in ("COMMIT TRANSACTION", "ROLLBACK TRANSACTION"):
                self.info._set(TransactionStatus.IDLE)

    adapter = PsycopgAdapter.__new__(PsycopgAdapter)
    adapter._debug_callback = None
    connection = _RecordingConnection()
    _bind_fake_connection(adapter, connection)

    adapter.begin_transaction("BEGIN TRANSACTION")

    assert connection.autocommit is True
    assert connection.statements == ["BEGIN TRANSACTION"]
    assert adapter.in_transaction is True

    adapter.begin_transaction("BEGIN TRANSACTION")
    assert connection.statements == ["BEGIN TRANSACTION"]

    adapter.commit_transaction("COMMIT TRANSACTION")
    assert connection.autocommit is True
    assert connection.statements == ["BEGIN TRANSACTION", "COMMIT TRANSACTION"]
    assert adapter.in_transaction is False


def test_sqlite_adapter_reports_connection_state() -> None:
    adapter = SQLiteAdapter(database_name=":memory:")
    assert adapter.is_connected() is True

    adapter.close()
    assert adapter.is_connected() is False


def test_sqlite_adapter_reconnect_opens_a_fresh_connection(tmp_path: Path) -> None:
    db_path = str(tmp_path / "reconnect.sqlite")
    adapter = SQLiteAdapter(database_name=db_path)
    adapter.exec("CREATE TABLE t (val INTEGER)")
    adapter.exec("INSERT INTO t (val) VALUES (1)")
    adapter.close()
    assert adapter.is_connected() is False

    adapter.reconnect()

    assert adapter.is_connected() is True
    rows = adapter.query("SELECT val FROM t").fetch_dicts()
    assert [row["val"] for row in rows] == [1]
    adapter.close()


def test_sqlite_adapter_reconnect_reapplies_startup_queries(tmp_path: Path) -> None:
    db_path = str(tmp_path / "startup.sqlite")
    adapter = SQLiteAdapter(
        database_name=db_path,
        startup_queries=["CREATE TABLE IF NOT EXISTS startup (id INTEGER)"],
        options={"foreign_keys": True},
    )
    adapter.close()

    adapter.reconnect()

    assert adapter.query("PRAGMA foreign_keys").scalar() == 1
    adapter.query("SELECT id FROM startup")
    adapter.close()


def test_database_reconnect_if_disconnected_is_a_noop_while_connected(tmp_path: Path) -> None:
    db = DB.connect_sqlite(str(tmp_path / "live.sqlite"))
    db.exec("CREATE TABLE t (val INTEGER)")

    assert db.is_connected() is True
    assert db.reconnect_if_disconnected() is False

    # Same connection, so the table created before the call is still there.
    db.query("SELECT val FROM t")
    db.close()


def test_database_reconnect_if_disconnected_restores_a_dropped_connection(tmp_path: Path) -> None:
    db = DB.connect_sqlite(str(tmp_path / "dropped.sqlite"))
    db.exec("CREATE TABLE t (val INTEGER)")
    db.insert("t").values({"val": 7}).execute()
    db.close()

    assert db.reconnect_if_disconnected() is True

    assert db.is_connected() is True
    assert db.select("t").execute().scalar() == 7
    db.close()


def test_database_reconnect_clears_savepoint_bookkeeping() -> None:
    adapter = _RecordingAdapter()
    db = DB(adapter, SQLiteDialect())

    db.begin_transaction()
    db.begin_transaction("sp1")
    assert db._savepoints == ["sp1"]

    adapter.close()
    assert db.reconnect_if_disconnected() is True

    assert db._savepoints == []
    assert adapter.connects == 1
