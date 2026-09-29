from __future__ import annotations

import pytest

from flowlab.modules.db import DB, QueryError, QueryWithParams
from flowlab.modules.db.adapters import SQLiteAdapter
from flowlab.modules.db.dialects import SQLDialect, SQLiteDialect
from flowlab.modules.db.query import InsertQuery


def test_insert_simple(sql_dialect: SQLDialect, mock_db) -> None:
    q = InsertQuery(sql_dialect, "users", database=mock_db)
    q.values({"name": "John", "age": 30})
    qwp: QueryWithParams = q.to_query_with_params()
    assert "INSERT INTO" in qwp.query
    assert '"name"' in qwp.query


def test_insert_multiple_rows(sql_dialect: SQLDialect, mock_db) -> None:
    q = InsertQuery(sql_dialect, "users", database=mock_db)
    q.values({"name": "John"}, {"name": "Jane"})
    qwp: QueryWithParams = q.to_query_with_params()
    assert "INSERT INTO" in qwp.query
    assert "VALUES" in qwp.query
    assert qwp.params == ["John", "Jane"]


def test_insert_with_on_conflict_do_nothing_is_a_noop_when_dialect_lacks_support(
    sql_dialect: SQLDialect, mock_db
) -> None:
    """PHP's base SQLDialect::ON_CONFLICT constant is false, so
    buildOnConflict() always returns early regardless of what was requested
    (Database/Dialects/SQLDialect.php `if (!$this->onConflict()) return;`).
    The base ANSI dialect must therefore silently drop the clause rather than
    render it."""
    q = InsertQuery(sql_dialect, "users", database=mock_db)
    q.values({"id": 1, "name": "John"})
    q.on_conflict_do_nothing(["id"])
    qwp: QueryWithParams = q.to_query_with_params()
    assert "ON CONFLICT" not in qwp.query


def test_insert_with_on_conflict_do_nothing(sqlite_dialect) -> None:
    """A dialect that *does* support ON CONFLICT (e.g. modern SQLite) renders
    the column-list clause."""
    from flowlab.modules.db.database import DatabaseABC

    class _MockDB(DatabaseABC):
        def __init__(self) -> None:
            pass

    q = InsertQuery(sqlite_dialect, "users", database=_MockDB())
    q.values({"id": 1, "name": "John"})
    q.on_conflict_do_nothing(["id"])
    qwp: QueryWithParams = q.to_query_with_params()
    assert 'ON CONFLICT ("id")' in qwp.query
    assert "DO NOTHING" in qwp.query


def test_insert_with_on_conflict_do_nothing_string_raises(sqlite_dialect) -> None:
    """SQLiteDialect::buildOnConflict() explicitly raises for named
    constraints (SQLite has no `ON CONSTRAINT` syntax); the base ANSI
    dialect does not (it never even reaches that branch)."""
    from flowlab.modules.db import QueryError
    from flowlab.modules.db.database import DatabaseABC

    class _MockDB(DatabaseABC):
        def __init__(self) -> None:
            pass

    q = InsertQuery(sqlite_dialect, "users", database=_MockDB())
    q.values({"id": 1, "name": "John"})
    q.on_conflict_do_nothing("users_pkey")
    with pytest.raises(QueryError, match="[Nn]amed"):
        q.to_query_with_params()


def test_insert_with_returning(sql_dialect: SQLDialect, mock_db) -> None:
    """Base ANSI dialect doesn't support RETURNING natively."""
    q = InsertQuery(sql_dialect, "users", database=mock_db)
    q.values({"name": "John"})
    q.returning(["id"])
    qwp: QueryWithParams = q.to_query_with_params()
    assert "INSERT INTO" in qwp.query


def test_insert_last_insert_id(sql_dialect: SQLDialect, mock_db) -> None:
    q = InsertQuery(sql_dialect, "users", database=mock_db)
    q.values({"name": "John"})
    q.last_insert_id("id")
    qwp: QueryWithParams = q.to_query_with_params()
    assert "INSERT" in qwp.query


def _legacy_sqlite_db() -> DB:
    """A database whose dialect predates RETURNING (SQLite 3.35) and ON
    CONFLICT (3.24). The version gate is what decides, so an old version number
    against a live in-memory database is enough to drive the emulated paths."""
    return DB(SQLiteAdapter(":memory:"), SQLiteDialect(version="3.23"))


def _users_table(db: DB) -> None:
    db.create_table("users").if_not_exists().identity("id").string("name").string("email").execute()


def test_returning_is_emulated_when_the_dialect_lacks_it() -> None:
    """RETURNING is emulated by anything that cannot express it -- the caller
    does not have to opt in, and never has to branch per driver."""
    db = _legacy_sqlite_db()
    _users_table(db)

    result = (
        db.insert("users")
        .values({"name": "John", "email": "john@x.com"})
        .returning(["id", "name"])
        .last_insert_id("id")
        .execute()
    )

    assert not isinstance(result, list)
    row = result.fetch_dict()
    assert row is not None
    assert row["name"] == "John"
    assert row["id"] == 1


def test_emulated_returning_without_a_primary_key_column_raises() -> None:
    """Reading the inserted row back needs the primary key column, and no row
    at all is a worse answer than a loud one."""
    db = _legacy_sqlite_db()
    _users_table(db)

    q = db.insert("users").values({"name": "John"}).returning(["id"])
    with pytest.raises(QueryError, match="last_insert_id"):
        q.execute()


def test_native_returning_is_left_to_the_dialect() -> None:
    """Modern SQLite has RETURNING, so nothing is emulated and no primary key
    column is needed."""
    db = DB.connect_sqlite(":memory:")
    _users_table(db)

    result = db.insert("users").values({"name": "John"}).returning(["id", "name"]).execute()

    assert not isinstance(result, list)
    assert result.fetch_dict() == {"id": 1, "name": "John"}


def test_emulate_returning_forces_emulation_on_a_native_dialect() -> None:
    """emulate_returning() is only for opting *into* the emulation on a dialect
    that would not have needed it."""
    db = DB.connect_sqlite(":memory:")
    _users_table(db)

    query = db.insert("users").values({"name": "John"}).returning(["id", "name"]).emulate_returning("id")
    assert "RETURNING" not in query.to_sql()

    result = query.execute()
    assert not isinstance(result, list)
    row = result.fetch_dict()
    assert row is not None
    assert row["name"] == "John"


def test_returning_survives_a_native_on_conflict() -> None:
    """A dialect with ON CONFLICT but no RETURNING keeps its conflict clause
    while the row is read back separately."""
    db = DB(SQLiteAdapter(":memory:"), SQLiteDialect(version="3.34"))
    _users_table(db)
    db.insert("users").values({"id": 1, "name": "John", "email": "john@x.com"}).execute()

    query = (
        db.insert("users")
        .values({"id": 1, "name": "Jane", "email": "jane@x.com"})
        .on_conflict_do_update(["id"])
        .returning(["id", "name"])
        .last_insert_id("id")
    )
    assert "ON CONFLICT" in query.to_sql()
    assert "RETURNING" not in query.to_sql()

    result = query.execute()
    assert not isinstance(result, list)
    row = result.fetch_dict()
    assert row is not None
    assert row["name"] == "Jane"


def test_on_conflict_is_emulated_when_the_dialect_lacks_it() -> None:
    """ON CONFLICT follows the same rule: emulated whenever the dialect cannot
    express it, without emulate_on_conflict() being called."""
    db = _legacy_sqlite_db()
    _users_table(db)
    db.insert("users").values({"id": 1, "name": "John", "email": "john@x.com"}).execute()

    db.insert("users").values({"id": 1, "name": "John", "email": "new@x.com"}).on_conflict_do_update(["id"]).execute()

    rows = db.select("users").execute().fetch_dicts()
    assert len(rows) == 1
    assert rows[0]["email"] == "new@x.com"
