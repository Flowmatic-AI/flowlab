"""Integration tests for flowlab.modules.db using SQLite in-memory database."""

from __future__ import annotations

from typing import Any

from flowlab.modules.db import DB, QueryWithParams
from flowlab.modules.db.adapters import SQLiteAdapter
from flowlab.modules.db.dialects import SQLiteDialect
from flowlab.modules.db.query.ddl import Column
from flowlab.modules.db.result import ResultABC


def test_sqlite_in_memory_crud() -> None:
    """Full CRUD integration test using SQLite in-memory database."""
    adapter = SQLiteAdapter(database_name=":memory:")
    version: str = adapter.version()
    dialect = SQLiteDialect(version=version)

    assert adapter.driver_name == "sqlite"
    assert len(version) > 0

    from flowlab.modules.db.query.enums import TypeEnum

    qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="users",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="name", type=TypeEnum.STRING, not_null=True),
            Column(name="email", type=TypeEnum.STRING),
            Column(name="age", type=TypeEnum.INT),
            Column(name="active", type=TypeEnum.BOOL, default=True),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    adapter.exec(qwp.query)

    result: ResultABC = adapter.query("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    rows: list[dict] = result.fetch_dicts()
    assert len(rows) == 1
    assert rows[0]["name"] == "users"

    qwp = dialect.insert(
        table="users",
        values=[
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 25},
            {"name": "Charlie", "email": "charlie@example.com", "age": 35},
        ],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    result = adapter.query_with_params(dialect, qwp)
    assert result is not None

    qwp = dialect.select(
        distinct=None,
        columns=None,
        table="users",
        joins=None,
        where=None,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    result = adapter.query_with_params(dialect, qwp)
    rows = result.fetch_dicts()
    assert len(rows) == 3

    from flowlab.modules.db.query import Condition
    from flowlab.modules.db.query.enums import ConditionEnum

    where: list[Condition] = [Condition(condition=ConditionEnum.EQUALS, identifier="name", value="Alice")]
    qwp = dialect.select(
        distinct=None,
        columns=["id", "name", "email"],
        table="users",
        joins=None,
        where=where,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    result = adapter.query_with_params(dialect, qwp)
    rows = result.fetch_dicts()
    assert len(rows) == 1
    assert rows[0]["name"] == "Alice"

    where = [Condition(condition=ConditionEnum.EQUALS, identifier="name", value="Bob")]
    qwp = dialect.update(
        table="users",
        updates={"age": 26},
        where=where,
        returning=None,
    )
    adapter.query_with_params(dialect, qwp)

    where = [Condition(condition=ConditionEnum.EQUALS, identifier="name", value="Bob")]
    qwp = dialect.select(
        distinct=None,
        columns=["age"],
        table="users",
        joins=None,
        where=where,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    result = adapter.query_with_params(dialect, qwp)
    row: dict[str, Any] | None = result.fetch_dict()
    assert row is not None
    assert row["age"] == 26

    where = [Condition(condition=ConditionEnum.EQUALS, identifier="name", value="Charlie")]
    qwp = dialect.delete(table="users", where=where, returning=None)
    adapter.query_with_params(dialect, qwp)

    qwp = dialect.select(
        distinct=None,
        columns=None,
        table="users",
        joins=None,
        where=None,
        group_by=None,
        having=None,
        order_by=None,
        limit=None,
        offset=None,
        unions=None,
    )
    result = adapter.query_with_params(dialect, qwp)
    rows = result.fetch_dicts()
    assert len(rows) == 2

    adapter.commit_transaction(dialect.commit_transaction().query)
    adapter.begin_transaction(dialect.begin_transaction().query)
    qwp = dialect.insert(
        table="users",
        values=[{"name": "Dave", "email": "dave@example.com", "age": 40}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    adapter.query_with_params(dialect, qwp)
    adapter.rollback_transaction(dialect.rollback_transaction().query)

    result = adapter.query("SELECT count(*) AS cnt FROM users")
    row = result.fetch_dict()
    assert row is not None
    assert row["cnt"] == 2

    db = DB(adapter, dialect)
    assert db.adapter is adapter
    assert db.dialect is dialect

    adapter.exec(dialect.drop_table(if_exists=True, table="users").query)
    adapter.close()


def test_database_connect_sqlite() -> None:
    """Test the DB.connect() factory method."""
    db = DB.connect_sqlite(":memory:")
    assert db is not None
    assert db.adapter.driver_name == "sqlite"
    assert db.dialect is not None
    assert db.in_transaction is False


def test_database_drivers() -> None:
    """Test the drivers() static method."""
    drivers: list[str] = DB.drivers()
    assert "sqlite" in drivers
    assert "postgresql" in drivers


def test_query_builder_select_integration() -> None:
    """Test SelectQuery with SQLite adapter."""
    adapter = SQLiteAdapter(database_name=":memory:")
    dialect = SQLiteDialect(version=adapter.version())

    from flowlab.modules.db.query.enums import TypeEnum

    qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="items",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="name", type=TypeEnum.STRING),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    adapter.exec(qwp.query)

    qwp = dialect.insert(
        table="items",
        values=[{"name": "Item A"}, {"name": "Item B"}, {"name": "Item C"}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    adapter.query_with_params(dialect, qwp)

    from flowlab.modules.db import DB
    from flowlab.modules.db.query import SelectQuery

    db = DB(adapter, dialect)
    q = SelectQuery(dialect, "items", database=db)
    q.columns(["id", "name"])
    q.where_greater_than("id", 1)
    q.order_by_asc("name")

    qwp = q.to_query_with_params()
    result = adapter.query_with_params(dialect, qwp)
    rows: list[dict] = result.fetch_dicts()
    assert len(rows) == 2

    q2 = SelectQuery(dialect, "items", database=db)
    q2.limit(1)
    qwp2: QueryWithParams = q2.to_query_with_params()
    result2 = adapter.query_with_params(dialect, qwp2)
    rows2: list[dict] = result2.fetch_dicts()
    assert len(rows2) == 1

    adapter.close()


def test_result_scalar() -> None:
    """Test scalar result fetching."""
    adapter = SQLiteAdapter(database_name=":memory:")

    adapter.exec("CREATE TABLE test (val INTEGER)")
    adapter.exec("INSERT INTO test VALUES (42)")

    result: ResultABC = adapter.query("SELECT val FROM test")
    val: Any = result.scalar()
    assert val == 42

    adapter.close()


def test_last_insert_id() -> None:
    """Test last insert ID."""
    adapter = SQLiteAdapter(database_name=":memory:")
    dialect = SQLiteDialect(version=adapter.version())

    from flowlab.modules.db.query.enums import TypeEnum

    qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="t",
        columns=[Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True)],
        primary_keys=["id"],
        constraints=None,
    )
    adapter.exec(qwp.query)

    adapter.exec("INSERT INTO t DEFAULT VALUES")
    lid: Any = adapter.last_insert_id()
    assert lid is not None
    assert lid >= 1

    adapter.close()


def test_sqlite_datetime_and_json_column_types() -> None:
    """DATETIME and JSON are custom sqlite3 datatypes: SQLite stores only
    primitives, so SQLiteAdapter registers adapters that serialize datetimes and
    documents on the way in and converters that rebuild them on the way out.
    """
    from datetime import date, datetime, timedelta, timezone

    from flowlab.modules.db.query.enums import TypeEnum

    adapter = SQLiteAdapter(database_name=":memory:")
    dialect = SQLiteDialect(version=adapter.version())

    qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="events",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="happened_at", type=TypeEnum.DATETIME),
            Column(name="payload", type=TypeEnum.JSON),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    assert '"happened_at" DATETIME' in qwp.query
    assert '"payload" JSON' in qwp.query
    adapter.exec(qwp.query)

    aware = datetime(2026, 8, 10, 12, 34, 56, 123456, tzinfo=timezone(timedelta(hours=2)))
    payload = {"kind": "signup", "tags": ["a", "b"], "meta": {"ok": True, "n": 3}}

    qwp = dialect.insert(
        table="events",
        values=[{"happened_at": aware, "payload": payload}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    adapter.query_with_params(dialect, qwp)

    result: ResultABC = adapter.query('SELECT "happened_at", "payload" FROM "events"')
    row: dict[str, Any] | None = result.fetch_dict()
    assert row is not None
    assert row["happened_at"] == aware
    assert row["payload"] == payload
    assert result.columns() == {"happened_at": "DATETIME", "payload": "JSON"}

    naive = datetime(2026, 1, 2, 3, 4, 5)  # noqa: DTZ001 - naive on purpose
    qwp = dialect.update(
        table="events",
        updates={"happened_at": naive, "payload": [1, "a", None]},
        where=None,
        returning=None,
    )
    adapter.query_with_params(dialect, qwp)
    row = adapter.query('SELECT "happened_at", "payload" FROM "events"').fetch_dict()
    assert row is not None
    assert row["happened_at"] == naive
    assert row["payload"] == [1, "a", None]

    adapter.exec('CREATE TABLE "days" ("d" DATE)')
    adapter.query_with_params(
        dialect, QueryWithParams(query='INSERT INTO "days" ("d") VALUES (?)', params=[date(2026, 8, 10)])
    )
    assert adapter.query('SELECT "d" FROM "days"').scalar() == date(2026, 8, 10)

    adapter.close()


def test_sqlite_declared_types_only_convert_table_columns() -> None:
    """PARSE_DECLTYPES keys off the column's declared type, so expressions and
    untyped columns are handed back exactly as SQLite stored them."""
    from datetime import datetime

    adapter = SQLiteAdapter(database_name=":memory:")

    adapter.exec('CREATE TABLE "t" ("ts" DATETIME, "note" TEXT, "n" INTEGER)')
    adapter.exec('INSERT INTO "t" VALUES (\'2026-08-10 12:00:00\', \'{"k": "v"}\', 7)')

    row: dict[str, Any] | None = adapter.query('SELECT "ts", "note", "n", count(*) AS "c" FROM "t"').fetch_dict()
    assert row is not None
    assert isinstance(row["ts"], datetime)
    assert row["note"] == '{"k": "v"}'
    assert row["n"] == 7
    assert row["c"] == 1

    adapter.close()


def test_sqlite_datetime_column_keeps_unparseable_values() -> None:
    """A DATETIME column can hold whatever SQLite accepted; a value the
    converter cannot read comes back as text instead of failing the fetch."""
    adapter = SQLiteAdapter(database_name=":memory:")

    adapter.exec('CREATE TABLE "t" ("ts" DATETIME)')
    adapter.exec("INSERT INTO \"t\" VALUES ('not a timestamp')")

    assert adapter.query('SELECT "ts" FROM "t"').scalar() == "not a timestamp"

    adapter.close()


def test_sqlite_works_without_any_optional_driver_installed() -> None:
    """The package promises SQLite out of the box, with no driver extra.

    That promise is broken by a single module-scope ``import <driver>`` anywhere
    under ``flowlab/modules/db/adapters``, because importing one adapter imports the
    package, which imports them all. Run in a subprocess with ``-S`` so that
    site-packages -- and with it every optional driver installed for the test
    suite itself -- is off the path, which is the only way to see what a plain
    ``pip install flowlab`` sees. The framework package itself is stubbed, because
    it depends on FastAPI; only the database module is under test."""
    import subprocess
    import sys
    from pathlib import Path

    src = Path(__file__).resolve().parents[3] / "src"
    program = (
        "import sys, types;"
        f"sys.path.insert(0, {str(src)!r});"
        "package = types.ModuleType('flowlab');"
        f"package.__path__ = [{str(src / 'flowlab')!r}];"
        "sys.modules['flowlab'] = package;"
        "from flowlab.modules.db.database import DB;"
        "db = DB.connect_sqlite(':memory:');"
        "db.exec('CREATE TABLE t (val INTEGER)');"
        "db.exec('INSERT INTO t (val) VALUES (1)');"
        "print(DB.drivers(), db.query('SELECT val FROM t').scalar())"
    )

    completed = subprocess.run(
        [sys.executable, "-S", "-c", program],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "['sqlite'] 1"
