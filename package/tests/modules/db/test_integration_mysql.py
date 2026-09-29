"""Integration tests for flowlab.modules.db using a real MySQL server (via Docker).

These tests require a running MySQL service reachable on ``localhost:3306``
with user ``root`` and an empty password (the standard ``mysql`` Docker image
launched with ``MYSQL_ALLOW_EMPTY_PASSWORD=yes``).  The ``flowlab_test`` database is
created automatically on the first run.

The suite mirrors ``tests/test_integration_sqlite.py`` but exercises the
MySQL-specific adapter, dialect and result set implementation:

    * ``MySQLAdapter`` — wraps ``mysql.connector`` and converts ``?`` to ``%s``.
    * ``MySQLDialect`` — backtick escaping, ``ON DUPLICATE KEY UPDATE`` instead
      of ``ON CONFLICT``, no ``RETURNING``, ``TINYINT`` booleans.
    * ``MySQLResult`` — cursor-backed result set.

Run with::

    python3 -m pytest tests/test_integration_mysql.py -v
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import pytest

from flowlab.modules.db import QueryError, QueryWithParams
from flowlab.modules.db.adapters import MySQLAdapter
from flowlab.modules.db.database import DB
from flowlab.modules.db.dialects import MySQLDialect
from flowlab.modules.db.query import OnConflict, SelectQuery
from flowlab.modules.db.query.ddl import (
    AddColumn,
    AddForeignKeyConstraint,
    AddUniqueConstraint,
    AlterColumn,
    Column,
    DropColumn,
    ForeignKeyConstraint,
    RenameColumn,
    UniqueConstraint,
)
from flowlab.modules.db.query.enums import ReferentialActionEnum, TypeEnum
from flowlab.modules.db.query.expressions import CurrentTimestamp
from flowlab.modules.db.result import ResultABC

MYSQL_HOST: str = "localhost"
MYSQL_PORT: int = 3306
MYSQL_USER: str = "root"
MYSQL_PASSWORD: str = ""
MYSQL_DATABASE: str = "flowlab_test"


@pytest.fixture(scope="session")
def _flowlab_test_database() -> None:
    """Ensure the ``flowlab_test`` database exists on the MySQL server.

    Connects to the server without selecting a database (using the ``mysql``
    system database) and issues ``CREATE DATABASE IF NOT EXISTS``.  The whole
    test module is skipped if MySQL is not reachable.
    """
    import mysql.connector

    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database="mysql",
        )
    except mysql.connector.Error as exc:
        pytest.skip(f"MySQL server not reachable on {MYSQL_HOST}:{MYSQL_PORT}: {exc}")

    try:
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}`")
        conn.commit()
        cursor.close()
    finally:
        conn.close()


@pytest.fixture
def mysql_adapter(_flowlab_test_database: None) -> Iterator[MySQLAdapter]:
    """Yield a fresh ``MySQLAdapter`` connected to the ``flowlab_test`` database.

    All user tables are dropped on teardown so each test starts from a clean
    schema, keeping the suite hermetic.
    """
    adapter = MySQLAdapter(
        database_name=MYSQL_DATABASE,
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
    )
    try:
        yield adapter
    finally:
        try:
            import mysql.connector

            try:
                adapter.rollback_transaction(MySQLDialect().rollback_transaction().query)
            except mysql.connector.Error:
                pass
            result: ResultABC = adapter.query("SHOW TABLES")
            rows: list[dict[str, Any]] = result.fetch_dicts()
            if rows:
                adapter.exec("SET FOREIGN_KEY_CHECKS = 0")
                for row in rows:
                    for table_name in row.values():
                        adapter.exec(f"DROP TABLE IF EXISTS `{table_name}`")
                adapter.exec("SET FOREIGN_KEY_CHECKS = 1")
        finally:
            adapter.close()


@pytest.fixture
def mysql_dialect(mysql_adapter: MySQLAdapter) -> MySQLDialect:
    """Return a ``MySQLDialect`` bound to the live server's version string."""
    return MySQLDialect(version=mysql_adapter.version())


def _create_users_table(adapter: MySQLAdapter, dialect: MySQLDialect) -> None:
    """Create a minimal ``users`` table for CRUD-style tests."""
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


def test_mysql_in_memory_crud(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """Full CRUD integration test using the live MySQL server.

    Exercises CREATE TABLE, multi-row INSERT, SELECT (all / filtered), UPDATE
    and DELETE through the dialect + adapter pair.
    """
    adapter, dialect = mysql_adapter, mysql_dialect

    assert adapter.driver_name == "mysql"
    version: str = adapter.version()
    assert len(version) > 0

    _create_users_table(adapter, dialect)

    result: ResultABC = adapter.query("SHOW TABLES")
    rows: list[dict[str, Any]] = result.fetch_dicts()
    table_names: list[str] = [str(v) for row in rows for v in row.values()]
    assert "users" in table_names

    qwp: QueryWithParams = dialect.insert(
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

    where: list[Any] = [Condition(condition=ConditionEnum.EQUALS, identifier="name", value="Alice")]
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


def test_mysql_database_connect(_flowlab_test_database: None) -> None:
    """The ``DB.connect("mysql", "flowlab_test")`` factory wires adapter + dialect."""
    db = DB.connect_mysql(
        MYSQL_DATABASE,
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
    )
    live_adapter: MySQLAdapter = cast(MySQLAdapter, db.adapter)
    try:
        assert db is not None
        assert live_adapter.driver_name == "mysql"
        assert db.dialect is not None
        assert db.in_transaction is False
    finally:
        live_adapter.close()


def test_mysql_query_builder_select(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """Exercise ``SelectQuery`` against MySQL with WHERE, ORDER BY and LIMIT."""
    adapter, dialect = mysql_adapter, mysql_dialect
    db = DB(adapter, dialect)

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

    q: SelectQuery = SelectQuery(dialect, "items", database=db)
    q.columns(["id", "name"])
    q.where_greater_than("id", 1)
    q.order_by_asc("name")

    qwp = q.to_query_with_params()
    result: ResultABC = adapter.query_with_params(dialect, qwp)
    rows: list[dict[str, Any]] = result.fetch_dicts()
    assert len(rows) == 2
    assert rows[0]["name"] == "Item B"
    assert rows[1]["name"] == "Item C"

    q2: SelectQuery = SelectQuery(dialect, "items", database=db)
    q2.limit(1)
    qwp2: QueryWithParams = q2.to_query_with_params()
    result2: ResultABC = adapter.query_with_params(dialect, qwp2)
    rows2: list[dict[str, Any]] = result2.fetch_dicts()
    assert len(rows2) == 1


def test_mysql_joins(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """Exercise inner, left, right and cross joins with ``.on()`` conditions."""
    adapter, dialect = mysql_adapter, mysql_dialect
    db = DB(adapter, dialect)

    users_qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="users",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="name", type=TypeEnum.STRING, not_null=True),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    adapter.exec(users_qwp.query)

    posts_qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="posts",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="user_id", type=TypeEnum.INT),
            Column(name="title", type=TypeEnum.STRING),
        ],
        primary_keys=["id"],
        constraints=[
            ForeignKeyConstraint(
                columns=["user_id"],
                ref_table="users",
                ref_columns=["id"],
                on_delete="CASCADE",
            )
        ],
    )
    adapter.exec(posts_qwp.query)

    adapter.query_with_params(
        dialect,
        dialect.insert(
            table="users",
            values=[{"name": "Alice"}, {"name": "Bob"}],
            on_conflict=None,
            returning=None,
            last_insert_id=None,
        ),
    )
    adapter.query_with_params(
        dialect,
        dialect.insert(
            table="posts",
            values=[
                {"user_id": 1, "title": "Alice post 1"},
                {"user_id": 1, "title": "Alice post 2"},
                {"user_id": 2, "title": "Bob post 1"},
            ],
            on_conflict=None,
            returning=None,
            last_insert_id=None,
        ),
    )

    q: SelectQuery = SelectQuery(dialect, "users", database=db)
    q.columns(["name", "title"])
    q.inner_join("posts", lambda join: join.on(["users", "id"], ["posts", "user_id"]))
    q.order_by_asc("title")

    qwp: QueryWithParams = q.to_query_with_params()
    result: ResultABC = adapter.query_with_params(dialect, qwp)
    rows: list[dict[str, Any]] = result.fetch_dicts()
    assert len(rows) == 3
    assert [r["title"] for r in rows] == ["Alice post 1", "Alice post 2", "Bob post 1"]

    adapter.query_with_params(
        dialect,
        dialect.insert(
            table="users",
            values=[{"name": "Carol"}],
            on_conflict=None,
            returning=None,
            last_insert_id=None,
        ),
    )

    q2: SelectQuery = SelectQuery(dialect, "users", database=db)
    q2.columns(["name", "title"])
    q2.left_join("posts", lambda join: join.on(["users", "id"], ["posts", "user_id"]))
    q2.order_by_asc("name")

    qwp2: QueryWithParams = q2.to_query_with_params()
    result2: ResultABC = adapter.query_with_params(dialect, qwp2)
    rows2: list[dict[str, Any]] = result2.fetch_dicts()
    assert len(rows2) == 4
    carol = [r for r in rows2 if r["name"] == "Carol"]
    assert len(carol) == 1
    assert carol[0]["title"] is None

    from flowlab.modules.db import raw as raw_expr

    q3: SelectQuery = SelectQuery(dialect, "users", database=db)
    q3.columns(["name", "title"])
    q3.join(raw_expr("RIGHT JOIN `posts` ON `users`.`id` = `posts`.`user_id`"))
    q3.order_by_asc("title")

    qwp3: QueryWithParams = q3.to_query_with_params()
    result3: ResultABC = adapter.query_with_params(dialect, qwp3)
    rows3: list[dict[str, Any]] = result3.fetch_dicts()
    assert len(rows3) == 3
    assert [r["title"] for r in rows3] == ["Alice post 1", "Alice post 2", "Bob post 1"]

    q4: SelectQuery = SelectQuery(dialect, "users", database=db)
    q4.columns(["name", "title"])
    q4.cross_join("posts")
    assert q4.joins[0].conditions == []

    qwp4: QueryWithParams = q4.to_query_with_params()
    result4: ResultABC = adapter.query_with_params(dialect, qwp4)
    rows4: list[dict[str, Any]] = result4.fetch_dicts()
    assert len(rows4) == 9


def test_mysql_conditions(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """Exercise the full ``where_*`` fluent API against MySQL."""
    adapter, dialect = mysql_adapter, mysql_dialect
    db = DB(adapter, dialect)

    qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="products",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="name", type=TypeEnum.STRING, not_null=True),
            Column(name="price", type=TypeEnum.INT),
            Column(name="category", type=TypeEnum.STRING),
            Column(name="in_stock", type=TypeEnum.BOOL, default=True),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    adapter.exec(qwp.query)

    adapter.query_with_params(
        dialect,
        dialect.insert(
            table="products",
            values=[
                {"name": "Widget", "price": 10, "category": "A", "in_stock": True},
                {"name": "Gadget", "price": 25, "category": "B", "in_stock": False},
                {"name": "Gizmo", "price": 50, "category": "A", "in_stock": True},
                {"name": "Thingy", "price": 75, "category": "C", "in_stock": None},
            ],
            on_conflict=None,
            returning=None,
            last_insert_id=None,
        ),
    )

    def _rows(q: SelectQuery) -> list[dict[str, Any]]:
        qwp_ = q.to_query_with_params()
        rows: list[dict[str, Any]] = adapter.query_with_params(dialect, qwp_).fetch_dicts()
        return rows

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_equals("name", "Widget")
    assert [r["name"] for r in _rows(q)] == ["Widget"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_in("category", ["A", "C"])
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gizmo", "Thingy", "Widget"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_between("price", 20, 60)
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gadget", "Gizmo"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_not_between("price", 20, 60)
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Thingy", "Widget"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_like("name", "G%")
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gadget", "Gizmo"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_starts_with("name", "Wi")
    assert [r["name"] for r in _rows(q)] == ["Widget"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_ends_with("name", "et")
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gadget", "Widget"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_contains("name", "adge")
    assert [r["name"] for r in _rows(q)] == ["Gadget"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_is_null("in_stock")
    assert [r["name"] for r in _rows(q)] == ["Thingy"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_is_not_null("in_stock")
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gadget", "Gizmo", "Widget"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_greater_than("price", 25)
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gizmo", "Thingy"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_less_than_or_equals("price", 25)
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gadget", "Widget"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_not_equals("category", "A")
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gadget", "Thingy"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_not_in("category", ["A"])
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gadget", "Thingy"]

    q = SelectQuery(dialect, "products", database=db).columns(["name"])
    q.where_regex("name", "^G.*o$")
    names = sorted(r["name"] for r in _rows(q))
    assert names == ["Gizmo"]


def test_mysql_transactions(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """Verify BEGIN/COMMIT/ROLLBACK and SAVEPOINT behaviour."""
    adapter, dialect = mysql_adapter, mysql_dialect

    qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="accounts",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="balance", type=TypeEnum.INT),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    adapter.exec(qwp.query)

    insert_qwp: QueryWithParams = dialect.insert(
        table="accounts",
        values=[{"balance": 100}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )

    def _count() -> int:
        """Read the current row count."""
        result: ResultABC = adapter.query("SELECT COUNT(*) AS cnt FROM accounts")
        row: dict[str, Any] | None = result.fetch_dict()
        assert row is not None
        return int(row["cnt"])

    assert _count() == 0

    adapter.begin_transaction(dialect.begin_transaction().query)
    assert adapter.in_transaction is True
    adapter.query_with_params(dialect, insert_qwp)
    adapter.rollback_transaction(dialect.rollback_transaction().query)
    assert adapter.in_transaction is False
    assert _count() == 0

    adapter.begin_transaction(dialect.begin_transaction().query)
    adapter.query_with_params(dialect, insert_qwp)
    adapter.commit_transaction(dialect.commit_transaction().query)
    assert adapter.in_transaction is False
    assert _count() == 1

    adapter.begin_transaction(dialect.begin_transaction().query)
    adapter.query_with_params(dialect, insert_qwp)

    adapter.begin_savepoint(dialect.begin_savepoint("sp1").query)
    adapter.query_with_params(dialect, insert_qwp)
    adapter.rollback_savepoint(dialect.rollback_savepoint("sp1").query)

    adapter.commit_transaction(dialect.commit_transaction().query)
    assert _count() == 2

    adapter.begin_transaction(dialect.begin_transaction().query)
    adapter.query_with_params(dialect, insert_qwp)

    adapter.begin_savepoint(dialect.begin_savepoint("sp2").query)
    adapter.query_with_params(dialect, insert_qwp)
    adapter.commit_savepoint(dialect.commit_savepoint("sp2").query)

    adapter.rollback_transaction(dialect.rollback_transaction().query)
    assert _count() == 2


def test_mysql_on_duplicate_key(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """``on_conflict_do_update`` renders as MySQL ``ON DUPLICATE KEY UPDATE``."""
    adapter, dialect = mysql_adapter, mysql_dialect

    qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="kv",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="key", type=TypeEnum.STRING, not_null=True),
            Column(name="value", type=TypeEnum.STRING),
        ],
        primary_keys=["id"],
        constraints=[UniqueConstraint(columns=["key"])],
    )
    adapter.exec(qwp.query)

    adapter.query_with_params(
        dialect,
        dialect.insert(
            table="kv",
            values=[{"key": "greeting", "value": "hello"}],
            on_conflict=None,
            returning=None,
            last_insert_id=None,
        ),
    )

    qwp = dialect.insert(
        table="kv",
        values=[{"key": "greeting", "value": "world"}],
        on_conflict=OnConflict(conflict="key", updates={"value": "world"}),
        returning=None,
        last_insert_id=None,
    )
    assert "ON DUPLICATE KEY UPDATE" in qwp.query
    adapter.query_with_params(dialect, qwp)

    result: ResultABC = adapter.query("SELECT COUNT(*) AS cnt FROM kv")
    row: dict[str, Any] | None = result.fetch_dict()
    assert row is not None
    assert row["cnt"] == 1

    result = adapter.query("SELECT `value` AS v FROM kv WHERE `key` = 'greeting'")
    row = result.fetch_dict()
    assert row is not None
    assert row["v"] == "world"

    qwp = dialect.insert(
        table="kv",
        values=[{"key": "greeting", "value": "ignored"}],
        on_conflict=OnConflict(conflict="key", updates=None),
        returning=None,
        last_insert_id=None,
    )
    assert qwp.query.startswith("INSERT IGNORE INTO ")
    adapter.query_with_params(dialect, qwp)

    result = adapter.query("SELECT `value` AS v FROM kv WHERE `key` = 'greeting'")
    row = result.fetch_dict()
    assert row is not None
    assert row["v"] == "world"

    qwp = dialect.insert(
        table="kv",
        values=[{"key": "greeting", "value": "from_values"}],
        on_conflict=OnConflict(conflict="key", updates={}),
        returning=None,
        last_insert_id=None,
    )
    adapter.query_with_params(dialect, qwp)
    result = adapter.query("SELECT `value` AS v FROM kv WHERE `key` = 'greeting'")
    row = result.fetch_dict()
    assert row is not None
    assert row["v"] == "from_values"


def test_mysql_alter_table(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """Exercise ADD / MODIFY / RENAME / DROP COLUMN + UNIQUE + FOREIGN KEY."""
    adapter, dialect = mysql_adapter, mysql_dialect

    parent_qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="categories",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="name", type=TypeEnum.STRING, not_null=True),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    adapter.exec(parent_qwp.query)

    child_qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="articles",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="title", type=TypeEnum.STRING, not_null=True),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    adapter.exec(child_qwp.query)

    for qwp_ in dialect.alter_table(
        "articles",
        [AddColumn(name="body", type=TypeEnum.STRING)],
    ):
        adapter.exec(qwp_.query)

    cols = _column_names(adapter, "articles")
    assert "body" in cols

    for qwp_ in dialect.alter_table(
        "articles",
        [AlterColumn(column="title", sql="VARCHAR(100)")],
    ):
        adapter.exec(qwp_.query)
    assert _column_type(adapter, "articles", "title") == "varchar(100)"

    for qwp_ in dialect.alter_table(
        "articles",
        [RenameColumn(old_name="title", new_name="headline")],
    ):
        adapter.exec(qwp_.query)
    cols = _column_names(adapter, "articles")
    assert "headline" in cols
    assert "title" not in cols

    for qwp_ in dialect.alter_table(
        "articles",
        [AddUniqueConstraint(columns=["body"], name="uq_articles_body")],
    ):
        adapter.exec(qwp_.query)
    assert _has_index(adapter, "articles", "uq_articles_body")

    for qwp_ in dialect.alter_table(
        "articles",
        [AddColumn(name="category_id", type=TypeEnum.INT)],
    ):
        adapter.exec(qwp_.query)

    for qwp_ in dialect.alter_table(
        "articles",
        [
            AddForeignKeyConstraint(
                columns=["category_id"],
                ref_table="categories",
                ref_columns=["id"],
                name="fk_articles_category",
                on_delete="CASCADE",
            )
        ],
    ):
        adapter.exec(qwp_.query)
    assert _has_fk(adapter, "articles", "fk_articles_category")

    for qwp_ in dialect.alter_table(
        "articles",
        [DropColumn(column="body")],
    ):
        adapter.exec(qwp_.query)
    cols = _column_names(adapter, "articles")
    assert "body" not in cols


def _column_names(adapter: MySQLAdapter, table: str) -> list[str]:
    """Return the column names of *table* in declaration order."""
    result: ResultABC = adapter.query(
        "SELECT `COLUMN_NAME` AS c FROM `information_schema`.`COLUMNS` "
        f"WHERE `TABLE_SCHEMA` = '{MYSQL_DATABASE}' AND `TABLE_NAME` = '{table}' "
        "ORDER BY `ORDINAL_POSITION`"
    )
    return [r["c"] for r in result.fetch_dicts()]


def _column_type(adapter: MySQLAdapter, table: str, column: str) -> str:
    """Return the lower-cased SQL column type string for *table.column*.

    Uses ``COLUMN_TYPE`` from ``information_schema`` so the full spec including
    length (e.g. ``varchar(100)``, ``decimal(10,2)``) is returned.
    """
    result: ResultABC = adapter.query(
        "SELECT `COLUMN_TYPE` AS t FROM `information_schema`.`COLUMNS` "
        f"WHERE `TABLE_SCHEMA` = '{MYSQL_DATABASE}' AND `TABLE_NAME` = '{table}' "
        f"AND `COLUMN_NAME` = '{column}'"
    )
    row: dict[str, Any] | None = result.fetch_dict()
    assert row is not None
    return str(row["t"]).lower()


def _has_index(adapter: MySQLAdapter, table: str, index_name: str) -> bool:
    result: ResultABC = adapter.query(
        "SELECT COUNT(*) AS cnt FROM `information_schema`.`STATISTICS` "
        f"WHERE `TABLE_SCHEMA` = '{MYSQL_DATABASE}' AND `TABLE_NAME` = '{table}' "
        f"AND `INDEX_NAME` = '{index_name}'"
    )
    row: dict[str, Any] | None = result.fetch_dict()
    return bool(row and int(row["cnt"]) > 0)


def _has_fk(adapter: MySQLAdapter, table: str, constraint_name: str) -> bool:
    result: ResultABC = adapter.query(
        "SELECT COUNT(*) AS cnt FROM `information_schema`.`KEY_COLUMN_USAGE` "
        f"WHERE `TABLE_SCHEMA` = '{MYSQL_DATABASE}' AND `TABLE_NAME` = '{table}' "
        f"AND `CONSTRAINT_NAME` = '{constraint_name}' "
        "AND `REFERENCED_TABLE_NAME` IS NOT NULL"
    )
    row: dict[str, Any] | None = result.fetch_dict()
    return bool(row and int(row["cnt"]) > 0)


def test_mysql_ddl(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """Create a table exercising every ``TypeEnum`` then drop it."""
    adapter, dialect = mysql_adapter, mysql_dialect

    qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="typed",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="flag", type=TypeEnum.BOOL, default=False),
            Column(name="score", type=TypeEnum.FLOAT),
            Column(name="label", type=TypeEnum.STRING, not_null=True),
            Column(name="created_at", type=TypeEnum.DATETIME),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    adapter.exec(qwp.query)

    cols = _column_names(adapter, "typed")
    assert cols == ["id", "flag", "score", "label", "created_at"]

    # TypeEnum.BOOL maps to a bare TINYINT (see MySQLDialect.type), so MySQL
    # reports no display width -- "tinyint(1)" would mean a BOOL/BOOLEAN column.
    assert _column_type(adapter, "typed", "flag") == "tinyint"

    adapter.query_with_params(
        dialect,
        dialect.insert(
            table="typed",
            values=[{"flag": True, "score": 1.5, "label": "row1", "created_at": None}],
            on_conflict=None,
            returning=None,
            last_insert_id=None,
        ),
    )
    result: ResultABC = adapter.query("SELECT `flag` AS f, `score` AS s FROM typed")
    row: dict[str, Any] | None = result.fetch_dict()
    assert row is not None
    assert row["f"] == 1
    assert float(row["s"]) == 1.5

    drop_qwp: QueryWithParams = dialect.drop_table(if_exists=True, table="typed")
    adapter.exec(drop_qwp.query)

    result = adapter.query("SHOW TABLES")
    rows: list[dict[str, Any]] = result.fetch_dicts()
    names = [str(v) for r in rows for v in r.values()]
    assert "typed" not in names


def test_mysql_giant_select(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """Build a maximal query exercising every supported SELECT feature."""
    adapter, dialect = mysql_adapter, mysql_dialect
    db = DB(adapter, dialect)

    users_qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="users",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="name", type=TypeEnum.STRING, not_null=True),
            Column(name="age", type=TypeEnum.INT),
            Column(name="email", type=TypeEnum.STRING),
        ],
        primary_keys=["id"],
        constraints=[UniqueConstraint(columns=["email"])],
    )
    adapter.exec(users_qwp.query)

    posts_qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="posts",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="user_id", type=TypeEnum.INT, not_null=True),
            Column(name="title", type=TypeEnum.STRING, not_null=True),
            Column(name="views", type=TypeEnum.INT),
        ],
        primary_keys=["id"],
        constraints=[
            ForeignKeyConstraint(
                columns=["user_id"],
                ref_table="users",
                ref_columns=["id"],
                on_delete="CASCADE",
            )
        ],
    )
    adapter.exec(posts_qwp.query)

    adapter.query_with_params(
        dialect,
        dialect.insert(
            table="users",
            values=[
                {"name": "Alice", "age": 30, "email": "alice@example.com"},
                {"name": "Bob", "age": 22, "email": "bob@example.com"},
                {"name": "Carol", "age": 40, "email": "carol@example.com"},
            ],
            on_conflict=None,
            returning=None,
            last_insert_id=None,
        ),
    )
    adapter.query_with_params(
        dialect,
        dialect.insert(
            table="posts",
            values=[
                {"user_id": 1, "title": "Hello World", "views": 100},
                {"user_id": 1, "title": "Second Post", "views": 50},
                {"user_id": 2, "title": "Bob Says Hi", "views": 10},
                {"user_id": 3, "title": "Carol Corner", "views": 999},
            ],
            on_conflict=None,
            returning=None,
            last_insert_id=None,
        ),
    )

    from flowlab.modules.db import identifier, raw

    q: SelectQuery = SelectQuery(dialect, "users", database=db)
    q.columns(
        [
            identifier(["users", "id"]),
            identifier(["users", "name"]),
            raw("COUNT(`posts`.`id`) AS post_count"),
            raw("SUM(`posts`.`views`) AS total_views"),
        ]
    )

    q.inner_join("posts", lambda join: join.on(["users", "id"], ["posts", "user_id"]))

    q.where_greater_than(["users", "age"], 18)
    q.where_in(["users", "id"], [1, 2, 3])
    q.where_not_in(["users", "name"], ["Zoe"])
    q.where_between(["users", "age"], 20, 45)
    q.where_like(["users", "email"], "%@example.com")
    q.where_is_not_null(["posts", "title"])
    q.where_starts_with(["users", "name"], "")
    q.where_ends_with(["users", "email"], ".com")
    q.where_contains(["users", "email"], "@")

    q.group_by([["users", "id"], ["users", "name"]])
    q.having_greater_than("post_count", 0)
    q.order_by_desc("total_views")
    q.limit(10)

    union_q: SelectQuery = SelectQuery(dialect, "users", database=db)
    union_q.columns(
        [
            identifier(["users", "id"]),
            identifier(["users", "name"]),
            raw("NULL AS post_count"),
            raw("NULL AS total_views"),
        ]
    )
    union_q.where_equals(["users", "name"], "Carol")
    q.union(union_q)

    qwp: QueryWithParams = q.to_query_with_params()

    assert qwp.query.startswith("(")
    assert "SELECT" in qwp.query
    assert "RETURNING" not in qwp.query
    assert "ON DUPLICATE" not in qwp.query
    assert "?" in qwp.query
    assert "INNER JOIN" in qwp.query
    assert "GROUP BY" in qwp.query
    assert "HAVING" in qwp.query
    assert "ORDER BY" in qwp.query
    assert "LIMIT" in qwp.query
    assert "UNION" in qwp.query
    assert "`users`.`id`" in qwp.query
    assert "`users`.`age`" in qwp.query

    result: ResultABC = adapter.query_with_params(dialect, qwp)
    rows: list[dict[str, Any]] = result.fetch_dicts()

    main_rows = [r for r in rows if r["post_count"] is not None]
    assert len(main_rows) == 3

    names_in_order = [r["name"] for r in main_rows]
    assert names_in_order == ["Carol", "Alice", "Bob"]

    carol = next(r for r in main_rows if r["name"] == "Carol")
    assert int(carol["post_count"]) == 1
    assert int(carol["total_views"]) == 999


def test_mysql_datetime_and_json_columns(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """Datetimes bind to DATETIME/TIMESTAMP and documents to JSON columns;
    mysql.connector returns datetimes natively while MySQLResult decodes the
    JSON columns it reports by type code.
    """
    from datetime import datetime

    adapter, dialect = mysql_adapter, mysql_dialect

    qwp: QueryWithParams = dialect.create_table(
        if_not_exists=False,
        table="docs",
        columns=[
            Column(name="id", type=TypeEnum.INT, auto_increment=True, not_null=True),
            Column(name="happened_at", type=TypeEnum.DATETIME, size=6),
            Column(name="payload", type=TypeEnum.JSON),
        ],
        primary_keys=["id"],
        constraints=None,
    )
    assert "`happened_at` DATETIME(6)" in qwp.query
    assert "`payload` JSON" in qwp.query
    adapter.exec(qwp.query)

    happened_at = datetime(2026, 8, 10, 12, 34, 56, 123456)  # noqa: DTZ001 - MySQL DATETIME is naive
    payload: dict[str, Any] = {"kind": "signup", "tags": ["a", "b"], "meta": {"ok": True, "n": 3}}

    qwp = dialect.insert(
        table="docs",
        values=[{"happened_at": happened_at, "payload": payload}],
        on_conflict=None,
        returning=None,
        last_insert_id=None,
    )
    adapter.query_with_params(dialect, qwp)

    result: ResultABC = adapter.query("SELECT `happened_at`, `payload` FROM `docs`")
    assert result.columns() == {"happened_at": "datetime", "payload": "json"}
    row: dict[str, Any] | None = result.fetch_dict()
    assert row is not None
    assert row["happened_at"] == happened_at
    assert row["payload"] == payload

    qwp = dialect.update(table="docs", updates={"payload": [1, "a", None]}, where=None, returning=None)
    adapter.query_with_params(dialect, qwp)
    assert adapter.query("SELECT `payload` FROM `docs`").scalar() == [1, "a", None]

    adapter.exec("ALTER TABLE `docs` ADD COLUMN `seen` TIMESTAMP(6) NULL")
    adapter.query_with_params(dialect, QueryWithParams(query="UPDATE `docs` SET `seen` = ?", params=[happened_at]))
    result = adapter.query("SELECT `seen` FROM `docs`")
    assert result.columns() == {"seen": "timestamp"}
    assert result.scalar() == happened_at


def test_mysql_threaded_access(_flowlab_test_database: None) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    db = DB.connect_mysql(
        MYSQL_DATABASE,
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
    )

    db.exec("DROP TABLE IF EXISTS `threaded`")
    db.exec("CREATE TABLE `threaded` (val INTEGER)")

    idents: set[int] = set()
    lock = threading.Lock()

    def _insert(value: int) -> None:
        db.insert("threaded").values({"val": value}).execute()
        row = db.select("threaded").where_equals("val", value).execute().fetch_dict()
        assert row is not None
        assert row["val"] == value
        with lock:
            idents.add(threading.get_ident())

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_insert, range(40)))

    rows = db.select("threaded").execute().fetch_dicts()
    assert sorted(row["val"] for row in rows) == list(range(40))
    # The pool has shut down, so every worker connection was closed as its
    # thread exited; only this thread's own connection is left.
    assert len(idents) > 1
    assert db.adapter.connection_count() == 1

    opened = threading.Event()
    release = threading.Event()

    def _holder() -> None:
        db.begin_transaction()
        opened.set()
        release.wait(timeout=10)
        db.rollback_transaction()

    holder = threading.Thread(target=_holder)
    holder.start()
    opened.wait(timeout=10)
    assert db.in_transaction is False
    release.set()
    holder.join()

    db.exec("DROP TABLE `threaded`")
    db.close()
    assert db.adapter.connection_count() == 0


def test_mysql_connection_limit(_flowlab_test_database: None) -> None:
    """Eight short-lived threads against three slots, one of which this thread
    already holds. Most have to queue, and each hands its slot on by exiting, so
    this only finishes if slots are really recycled -- and the peak proves the
    cap held while they did."""
    import threading

    db = DB.connect_mysql(
        MYSQL_DATABASE,
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        max_concurrent_connections=3,
        acquire_connection_timeout=60.0,
    )

    assert db.adapter.max_concurrent_connections == 3

    db.exec("DROP TABLE IF EXISTS `capped`")
    db.exec("CREATE TABLE `capped` (val INTEGER)")

    peak = 0
    lock = threading.Lock()
    done: list[int] = []

    def _work(index: int) -> None:
        nonlocal peak
        for value in range(index * 5, index * 5 + 5):
            db.insert("capped").values({"val": value}).execute()
            with lock:
                peak = max(peak, db.adapter.connection_count())
        with lock:
            done.append(index)

    threads = [threading.Thread(target=_work, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive()

    assert sorted(done) == list(range(8))
    assert peak == 3

    rows = db.select("capped").execute().fetch_dicts()
    assert sorted(row["val"] for row in rows) == list(range(40))

    db.exec("DROP TABLE `capped`")
    db.close()
    assert db.adapter.connection_count() == 0


def _introspection_schema(db: DB) -> None:
    """(Re)create the roles/users pair the introspection tests describe."""
    db.exec("DROP TABLE IF EXISTS `intro_users`")
    db.exec("DROP TABLE IF EXISTS `intro_roles`")

    db.create_table("intro_roles").identity("id").string("code", 10, not_null=True).execute()
    db.create_table("intro_users").identity("id").string("name", 64, not_null=True, default="anon").string(
        "email", 120
    ).integer("role_id").unique_constraint(["email"], name="intro_users_email_key").unique_constraint(
        ["name", "email"], name="intro_users_pair_key"
    ).foreign_key_constraint(
        "role_id",
        "intro_roles",
        "id",
        name="intro_users_role_fk",
        on_delete=ReferentialActionEnum.CASCADE,
        on_update=ReferentialActionEnum.SET_NULL,
    ).execute()


def test_mysql_describe_table(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """describe_table() reads columns and constraints out of information_schema."""
    db = DB(mysql_adapter, mysql_dialect)
    _introspection_schema(db)

    description = db.describe_table("intro_users")

    assert [column.name for column in description.columns] == ["id", "name", "email", "role_id"]
    assert description.columns[0].auto_increment is True
    assert description.columns[0].default is None
    assert description.columns[1].not_null is True
    assert description.columns[1].type == TypeEnum.STRING
    assert description.columns[1].size == 64
    assert description.columns[1].default == "anon"
    assert description.columns[2].not_null is False

    unique = {constraint.name: constraint.columns for constraint in description.constraints.unique}
    assert unique == {
        "intro_users_email_key": ["email"],
        "intro_users_pair_key": ["name", "email"],
    }

    assert len(description.constraints.foreign_keys) == 1
    foreign_key = description.constraints.foreign_keys[0]
    assert foreign_key.name == "intro_users_role_fk"
    assert foreign_key.columns == ["role_id"]
    assert foreign_key.ref_table == "intro_roles"
    assert foreign_key.ref_columns == ["id"]
    assert foreign_key.on_delete is ReferentialActionEnum.CASCADE
    assert foreign_key.on_update is ReferentialActionEnum.SET_NULL

    assert db.describe_table([MYSQL_DATABASE, "intro_users"]).columns == description.columns
    assert db.describe_table("no_such_table").columns == []


def test_mysql_list_tables(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """list_tables() reports the connected database and ignores the schema."""
    db = DB(mysql_adapter, mysql_dialect)
    _introspection_schema(db)

    assert db.list_tables() == ["intro_roles", "intro_users"]
    assert db.list_tables("public") == db.list_tables()


def test_mysql_create_and_drop_index(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """CREATE/DROP INDEX round-trip; MySQL rejects the IF (NOT) EXISTS guards."""
    db = DB(mysql_adapter, mysql_dialect)
    _introspection_schema(db)

    db.create_index("intro_users", "idx_intro_users_name").columns("name").execute()

    indexes = db.prepared(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?",
        ["intro_users"],
    ).scalars()
    assert "idx_intro_users_name" in indexes

    with pytest.raises(QueryError):
        db.create_index("intro_users", "idx_other").columns("name").if_not_exists().execute()

    with pytest.raises(QueryError):
        db.drop_index("intro_users", "idx_intro_users_name").if_exists().execute()

    db.drop_index("intro_users", "idx_intro_users_name").execute()

    indexes = db.prepared(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?",
        ["intro_users"],
    ).scalars()
    assert "idx_intro_users_name" not in indexes


def test_mysql_describe_table_primary_keys(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """MySQL names every primary key PRIMARY, so the key comes back by its columns."""
    db = DB(mysql_adapter, mysql_dialect)
    _introspection_schema(db)
    db.exec("DROP TABLE IF EXISTS `intro_memberships`")
    db.create_table("intro_memberships").integer("user_id").integer("role_id").primary_keys(
        ["user_id", "role_id"]
    ).execute()

    try:
        assert db.describe_table("intro_users").primary_keys == ["id"]
        assert db.describe_table("intro_memberships").primary_keys == ["user_id", "role_id"]
        assert db.describe_table("no_such_table").primary_keys == []

        # The PRIMARY rows must not have leaked into the other constraint lists.
        description = db.describe_table("intro_memberships")
        assert description.constraints.unique == []
        assert description.constraints.foreign_keys == []
    finally:
        db.exec("DROP TABLE IF EXISTS `intro_memberships`")
        db.exec("DROP TABLE IF EXISTS `intro_users`")
        db.exec("DROP TABLE IF EXISTS `intro_roles`")


def test_mysql_create_table_from_a_description(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """A description rebuilds its table in another database, constraints and all."""
    db = DB(mysql_adapter, mysql_dialect)
    _introspection_schema(db)
    db.exec("DROP DATABASE IF EXISTS flowlab_test_copy")
    db.exec("CREATE DATABASE flowlab_test_copy")

    try:
        for table in ["intro_roles", "intro_users"]:
            description = db.describe_table(table)
            description.table = ["flowlab_test_copy", table]
            assert isinstance(description.create_table(db), ResultABC)

        original = db.describe_table("intro_users")
        copy = db.describe_table(["flowlab_test_copy", "intro_users"])

        assert copy.columns == original.columns
        assert copy.primary_keys == original.primary_keys == ["id"]
        assert copy.constraints.unique == original.constraints.unique
        assert copy.constraints.foreign_keys == original.constraints.foreign_keys

        db.describe_table(["flowlab_test_copy", "intro_users"]).create_table(db, if_not_exists=True)
    finally:
        db.exec("DROP DATABASE IF EXISTS flowlab_test_copy")
        db.exec("DROP TABLE IF EXISTS `intro_users`")
        db.exec("DROP TABLE IF EXISTS `intro_roles`")


def test_mysql_describe_table_indexes(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """describe_table() reports the standalone indexes, and only those."""
    db = DB(mysql_adapter, mysql_dialect)
    _introspection_schema(db)
    db.create_index("intro_users", "idx_intro_users_role").columns("role_id").execute()

    try:
        description = db.describe_table("intro_users")

        assert [(index.name, index.columns, index.unique) for index in description.indexes] == [
            ("idx_intro_users_role", ["role_id"], False),
        ]

        # MySQL builds an index for every unique constraint and for every foreign
        # key, and both are described as the constraint they belong to.
        assert [index.name for index in description.indexes] == ["idx_intro_users_role"]
        assert sorted(constraint.name for constraint in description.constraints.unique) == [
            "intro_users_email_key",
            "intro_users_pair_key",
        ]

        # A unique index is a unique constraint on MySQL — the engine makes no
        # distinction — so it describes as one rather than as an index.
        db.create_index("intro_users", "idx_intro_users_pair").columns(["name", "email"]).unique().execute()
        described = db.describe_table("intro_users")

        assert [index.name for index in described.indexes] == ["idx_intro_users_role"]
        assert "idx_intro_users_pair" in [constraint.name for constraint in described.constraints.unique]
    finally:
        db.exec("DROP TABLE IF EXISTS `intro_users`")
        db.exec("DROP TABLE IF EXISTS `intro_roles`")


def test_mysql_create_table_from_a_description_replays_the_indexes(
    mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect
) -> None:
    """An index name is per table on MySQL, so a copy keeps the names it described."""
    db = DB(mysql_adapter, mysql_dialect)
    _introspection_schema(db)
    db.create_index("intro_users", "idx_intro_users_role").columns("role_id").execute()

    try:
        description = db.describe_table("intro_users")
        description.create_table(db, override_name="intro_users_copy", skip_foreign_key_constraints=True)

        copy = db.describe_table("intro_users_copy")

        assert [(index.name, index.columns, index.unique) for index in copy.indexes] == [
            ("idx_intro_users_role", ["role_id"], False),
        ]

        description.create_table(
            db,
            override_name="intro_users_bare",
            skip_foreign_key_constraints=True,
            skip_indexes=True,
        )

        assert db.describe_table("intro_users_bare").indexes == []
        assert [index.name for index in description.indexes] == ["idx_intro_users_role"]
    finally:
        db.exec("DROP TABLE IF EXISTS `intro_users_bare`")
        db.exec("DROP TABLE IF EXISTS `intro_users_copy`")
        db.exec("DROP TABLE IF EXISTS `intro_users`")
        db.exec("DROP TABLE IF EXISTS `intro_roles`")


def test_mysql_index_and_describe_with_a_qualified_table(
    mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect
) -> None:
    """A database-qualified table reaches both the index grammar and introspection."""
    db = DB(mysql_adapter, mysql_dialect)
    table = [MYSQL_DATABASE, "qual_metrics"]

    db.exec(f"DROP TABLE IF EXISTS `{MYSQL_DATABASE}`.`qual_metrics`")
    db.create_table(table).identity("id").string("kind", 32, not_null=True).execute()

    db.create_index(table, "idx_qual_kind").columns("kind").execute()

    indexes = db.prepared(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
        [MYSQL_DATABASE, "qual_metrics"],
    ).scalars()
    assert "idx_qual_kind" in indexes

    description = db.describe_table(table)
    assert [column.name for column in description.columns] == ["id", "kind"]
    assert description.columns[0].auto_increment is True

    db.drop_index(table, "idx_qual_kind").execute()

    indexes = db.prepared(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
        [MYSQL_DATABASE, "qual_metrics"],
    ).scalars()
    assert "idx_qual_kind" not in indexes


def test_mysql_describe_table_recovers_every_type_enum(
    mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect
) -> None:
    """A column declared through the builders describes back as it was declared.

    MySQL keeps every width, DATETIME(6) precision included.
    """
    db = DB(mysql_adapter, mysql_dialect)
    db.exec("DROP TABLE IF EXISTS `spread_types`")
    db.create_table("spread_types").identity("id").boolean("flag").integer("n32", 32).integer("n64", 64).float(
        "f32", 32
    ).float("f64", 64).string("s64", 64).string("s255").text("body").datetime("seen_at").json("payload").execute()

    columns = db.describe_table("spread_types").columns

    assert [(column.name, column.type, column.size) for column in columns] == [
        ("id", TypeEnum.INT, 64),
        ("flag", TypeEnum.BOOL, None),
        ("n32", TypeEnum.INT, 32),
        ("n64", TypeEnum.INT, 64),
        ("f32", TypeEnum.FLOAT, 32),
        ("f64", TypeEnum.FLOAT, 64),
        ("s64", TypeEnum.STRING, 64),
        ("s255", TypeEnum.STRING, 255),
        # text() asks for the widest string there is; on MySQL that is LONGTEXT,
        # which is bounded, so what comes back is that bound.
        ("body", TypeEnum.STRING, 4294967295),
        ("seen_at", TypeEnum.DATETIME, 6),
        ("payload", TypeEnum.JSON, None),
    ]


def test_mysql_describe_table_recovers_every_default(mysql_adapter: MySQLAdapter, mysql_dialect: MySQLDialect) -> None:
    """A default describes back as the Python value it was declared with.

    MySQL alone reports the value rather than the literal that spelled it, so
    there are no quotes for the dialect to strip. TEXT and JSON columns are
    absent because MySQL refuses a DEFAULT on either.
    """
    db = DB(mysql_adapter, mysql_dialect)
    db.exec("DROP TABLE IF EXISTS `spread_defaults`")
    db.create_table("spread_defaults").identity("id").boolean("flag", default=False).integer("n", default=42).float(
        "f", default=1.5
    ).string("s", 64, default="no way").string("s_quote", 64, default="it's here").string(
        "s_empty", 64, default=""
    ).datetime("seen_at", default=CurrentTimestamp()).integer("plain").execute()

    defaults = {column.name: column.default for column in db.describe_table("spread_defaults").columns}

    assert defaults["flag"] is False
    assert defaults["n"] == 42
    assert defaults["f"] == 1.5
    assert defaults["s"] == "no way"
    assert defaults["s_quote"] == "it's here"
    assert defaults["s_empty"] == ""
    assert isinstance(defaults["seen_at"], CurrentTimestamp)
    assert defaults["id"] is None
    assert defaults["plain"] is None
