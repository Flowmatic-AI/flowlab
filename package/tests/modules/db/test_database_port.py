"""Regression tests for PHP -> Python hand-port bugs in flowlab.modules.db.database.

Each test targets a specific behavioral mistranslation found by comparing
Database/Database.php, Database/Databases/DatabaseAbstract.php and
Database/Queries/Table.php against src/flowlab/modules/db/database/*.py.
"""

from __future__ import annotations

from typing import Any

from flowlab.modules.db.database import DB, Table


def _fresh_db() -> DB:
    return DB.connect_sqlite(":memory:")


def _sqlite_master_tables(db: DB) -> list[dict[str, Any]]:
    """Return the `sqlite_master` rows describing the tables that exist."""
    return db.query("SELECT `name` FROM `sqlite_master` WHERE `type` = 'table'").fetch_dicts()


def _create_users_table(db: DB) -> None:
    db.create_table("users").if_not_exists().identity("id").string("name").string("email").integer(
        "age", not_null=False
    ).execute()


def _create_users_table_unique_name(db: DB) -> None:
    """Real `ON CONFLICT (name)` requires an actual UNIQUE/PRIMARY KEY
    constraint on that column at the DB level -- unlike the old select-then-
    branch approach, the database itself enforces (and is the source of
    truth for) the conflict target."""
    db.create_table("users").if_not_exists().identity("id").string("name").string("email").integer(
        "age", not_null=False
    ).unique_constraint(["name"]).execute()


def _create_users_table_unique_name_email(db: DB) -> None:
    """Same as above but for a composite (name, email) conflict target."""
    db.create_table("users").if_not_exists().identity("id").string("name").string("email").integer(
        "age", not_null=False
    ).unique_constraint(["name", "email"]).execute()


def test_begin_transaction_uses_savepoints_when_nested() -> None:
    """DatabaseAbstract::beginTransaction nests via SAVEPOINT once already in a
    transaction; the port previously decided savepoint-vs-transaction purely
    from whether a `name` was passed, and never tracked nesting depth."""
    db = _fresh_db()

    assert db.in_transaction is False

    db.begin_transaction()
    assert db.in_transaction is True
    assert db._savepoints == []

    db.begin_transaction()
    assert db._savepoints == ["savepoint_1"]

    db.begin_transaction("named")
    assert db._savepoints == ["savepoint_1", "named"]

    db.commit_transaction()
    assert db._savepoints == ["savepoint_1"]

    db.commit_transaction()
    assert db._savepoints == []
    assert db.in_transaction is True

    db.commit_transaction()
    assert db.in_transaction is False


def test_commit_transaction_release_savepoints_clears_stack() -> None:
    db = _fresh_db()

    db.begin_transaction()
    db.begin_transaction()
    db.begin_transaction()
    assert len(db._savepoints) == 2

    db.commit_transaction(release_savepoints=True)
    assert db._savepoints == []
    assert db.in_transaction is False


def test_rollback_transaction_pops_savepoint_without_full_rollback() -> None:
    db = _fresh_db()
    _create_users_table(db)

    db.begin_transaction()
    db.insert("users").values({"name": "a", "email": "a@x.com"}).execute()

    db.begin_transaction()
    db.insert("users").values({"name": "b", "email": "b@x.com"}).execute()
    db.rollback_transaction()

    assert db.in_transaction is True
    assert db._savepoints == []

    rows = db.select("users").execute().fetch_dicts()
    assert [r["name"] for r in rows] == ["a"]

    db.commit_transaction()
    assert db.in_transaction is False


def test_query_with_params_falls_back_to_plain_query_without_params() -> None:
    """DatabaseAbstract::queryWithParams only calls the adapter's parameterized
    path when params is non-empty; otherwise it runs `adapter->query()`
    directly. The port always called the parameterized path."""
    db = _fresh_db()
    _create_users_table(db)

    from flowlab.modules.db import QueryWithParams

    result = db.query_with_params(QueryWithParams(query="SELECT 1 AS one"))
    row = result.fetch_dict()
    assert row == {"one": 1}


def test_prepared_defaults_params_to_empty_list() -> None:
    """Table.prepared(query, params=[], ...) has a default in PHP; the port
    made `params` a required positional argument."""
    db = _fresh_db()
    result = db.prepared("SELECT 1 AS one")
    assert result.fetch_dict() == {"one": 1}


def test_database_table_factory_method() -> None:
    """DatabaseAbstract::table() was missing entirely from the Python port."""
    db = _fresh_db()
    table = db.table("users")
    assert isinstance(table, Table)


def test_table_create_returns_unexecuted_query() -> None:
    """Table::create()/createIfNotExists() return the CreateTableQuery for the
    caller to execute; the port executed it eagerly and returned a Result."""
    db = _fresh_db()
    table = db.table("widgets")

    query = table.create_if_not_exists(lambda q: q.identity("id").string("name"))
    assert not any(t["name"] == "widgets" for t in _sqlite_master_tables(db))

    query.execute()
    assert any(t["name"] == "widgets" for t in _sqlite_master_tables(db))


def test_table_drop_returns_unexecuted_query() -> None:
    """Table::drop()/dropIfExists() return the DropTableQuery unexecuted."""
    db = _fresh_db()
    _create_users_table(db)

    table = db.table("users")
    query = table.drop_if_exists()

    assert any(t["name"] == "users" for t in _sqlite_master_tables(db))

    query.execute()
    assert not any(t["name"] == "users" for t in _sqlite_master_tables(db))


def test_table_columns_uses_generic_select_introspection() -> None:
    """Table::columns() selects with limit(0) and reads the result's column
    names, generically across all drivers. The port hardcoded a PRAGMA/
    information_schema query built with unescaped string interpolation."""
    db = _fresh_db()
    _create_users_table(db)

    columns = db.table("users").columns()
    assert set(columns) == {"id", "name", "email", "age"}


def test_table_is_empty_uses_correct_conventional_semantics() -> None:
    """Table::isEmpty() in the PHP source literally returns
    `$this->select()->limit(1)->count() > 0`, i.e. true when the table is
    NOT empty (an upstream PHP naming bug). This is a reviewed, intentional
    deviation from Table.php: is_empty() must return True when the table
    IS empty."""
    db = _fresh_db()
    _create_users_table(db)

    table = db.table("users")
    assert table.is_empty() is True

    table.insert({"name": "a", "email": "a@x.com"}).execute()
    assert table.is_empty() is False


def test_table_select_or_insert_matches_on_all_given_columns() -> None:
    """Table::selectOrInsert() builds a whereGroup over every column in
    `$columns`, keyed against `$values`. The port only ever matched on the
    first column/value pair."""
    db = _fresh_db()
    _create_users_table(db)

    table = db.table("users")
    table.insert({"name": "a", "email": "a@x.com", "age": 20}).execute()
    table.insert({"name": "a", "email": "other@x.com", "age": 30}).execute()

    result = table.select_or_insert(
        ["name", "email"],
        {"name": "a", "email": "other@x.com", "age": 30},
    )
    rows = result.fetch_dicts()
    assert len(rows) == 1
    assert rows[0]["age"] == 30
    assert len(db.select("users").execute().fetch_dicts()) == 2


def test_table_insert_or_ignore_uses_on_conflict_do_nothing() -> None:
    """Table::insertOrIgnore() is a plain alias for selectOrInsert() in
    Table.php. Reviewed decision: deliberately diverge from that and build
    an atomic `INSERT ... ON CONFLICT (columns) DO NOTHING` through
    InsertQuery instead, matching on every column passed in (not just the
    first) as the conflict target."""
    db = _fresh_db()
    _create_users_table_unique_name_email(db)

    table = db.table("users")
    table.insert_or_ignore(["name", "email"], {"name": "a", "email": "a@x.com", "age": 1})
    table.insert_or_ignore(["name", "email"], {"name": "a", "email": "a@x.com", "age": 2})

    rows = db.select("users").execute().fetch_dicts()
    assert len(rows) == 1
    assert rows[0]["age"] == 1


def test_table_insert_or_ignore_conflict_target_is_all_given_columns() -> None:
    """Matching on `name` alone would treat the second insert below as a
    conflict (same name) and drop it; insert_or_ignore must build its
    ON CONFLICT target from every column in `columns`, so a row that only
    shares `name` (but not `email`) is a distinct row and gets inserted."""
    db = _fresh_db()
    _create_users_table_unique_name_email(db)

    table = db.table("users")
    table.insert_or_ignore(["name", "email"], {"name": "a", "email": "a@x.com", "age": 1})
    table.insert_or_ignore(["name", "email"], {"name": "a", "email": "other@x.com", "age": 2})

    rows = db.select("users").execute().fetch_dicts()
    assert len(rows) == 2
    assert {row["email"] for row in rows} == {"a@x.com", "other@x.com"}


def test_table_insert_or_update_updates_existing_row() -> None:
    """Table::insertOrUpdate() in Table.php selects first, then either
    updates the matching row or inserts a new one. Reviewed decision:
    deliberately diverge from that and build an atomic
    `INSERT ... ON CONFLICT (columns) DO UPDATE` through InsertQuery
    instead -- no select-then-write race window."""
    db = _fresh_db()
    _create_users_table_unique_name(db)

    table = db.table("users")
    table.insert_or_update(["name"], {"name": "a", "email": "a@x.com", "age": 1})
    table.insert_or_update(["name"], {"name": "a", "email": "a@x.com", "age": 2})

    rows = db.select("users").execute().fetch_dicts()
    assert len(rows) == 1
    assert rows[0]["age"] == 2


def test_table_insert_or_update_conflict_target_is_all_given_columns() -> None:
    """insert_or_update must match on every column in `columns` (a composite
    key), not just the first -- otherwise a row sharing only the first
    column would be wrongly treated as the same conflicting row."""
    db = _fresh_db()
    _create_users_table_unique_name_email(db)

    table = db.table("users")
    table.insert_or_update(["name", "email"], {"name": "a", "email": "a@x.com", "age": 1})
    table.insert_or_update(["name", "email"], {"name": "a", "email": "other@x.com", "age": 2})

    rows = db.select("users").execute().fetch_dicts()
    assert len(rows) == 2
    ages_by_email = {row["email"]: row["age"] for row in rows}
    assert ages_by_email == {"a@x.com": 1, "other@x.com": 2}

    table.insert_or_update(["name", "email"], {"name": "a", "email": "a@x.com", "age": 99})
    rows = db.select("users").execute().fetch_dicts()
    assert len(rows) == 2
    ages_by_email = {row["email"]: row["age"] for row in rows}
    assert ages_by_email == {"a@x.com": 99, "other@x.com": 2}


def test_table_insert_or_ignore_and_insert_or_update_emit_on_conflict_sql() -> None:
    """insert_or_ignore()/insert_or_update() must be expressed as a single
    atomic `INSERT ... ON CONFLICT` upsert via InsertQuery's
    on_conflict_do_nothing()/on_conflict_do_update() builder methods, not a
    hand-written select-then-insert-or-update round trip. Assert the actual
    SQL text, using the same builder path Table.insert_or_ignore/
    insert_or_update go through internally."""
    db = _fresh_db()

    ignore_sql = (
        db.insert("users")
        .values({"name": "a", "email": "a@x.com", "age": 1})
        .on_conflict_do_nothing(["name", "email"])
        .to_sql()
    )
    assert "ON CONFLICT" in ignore_sql
    assert "DO NOTHING" in ignore_sql
    assert "name" in ignore_sql and "email" in ignore_sql

    update_sql = (
        db.insert("users")
        .values({"name": "a", "email": "a@x.com", "age": 1})
        .on_conflict_do_update(["name", "email"])
        .to_sql()
    )
    assert "ON CONFLICT" in update_sql
    assert "DO UPDATE SET" in update_sql
    assert "name" in update_sql and "email" in update_sql


def test_table_truncate_delegates_to_delete() -> None:
    """Table::truncate() is just `$this->delete()->execute()`. The port
    hand-built a dialect-level delete call bypassing the query builder."""
    db = _fresh_db()
    _create_users_table(db)

    table = db.table("users")
    table.insert({"name": "a", "email": "a@x.com"}).execute()
    assert len(db.select("users").execute().fetch_dicts()) == 1

    table.truncate()
    assert len(db.select("users").execute().fetch_dicts()) == 0


def test_table_copy_from_filters_columns_and_counts_rows() -> None:
    """Table::copyFrom()/copyTo() were missing entirely from the port.

    copyFrom() filters the (optionally mapped) row against the SOURCE table's
    own column list -- this guards against a `map` callback introducing keys
    that don't belong on the source, it does not adapt to the target table's
    schema. So to copy into a narrower target table, `map` must do the
    narrowing itself.
    """
    db = _fresh_db()
    _create_users_table(db)
    db.create_table("users_archive").if_not_exists().identity("id").string("name").execute()

    users = db.table("users")
    users.insert({"name": "a", "email": "a@x.com", "age": 1}).execute()
    users.insert({"name": "b", "email": "b@x.com", "age": 2}).execute()

    archive = db.table("users_archive")
    count = archive.copy_from(users, map=lambda row: {"name": row["name"], "bogus": "not-a-source-column"})

    assert count == 2
    archived_names = {row["name"] for row in db.select("users_archive").execute().fetch_dicts()}
    assert archived_names == {"a", "b"}


def test_database_drivers_reflects_real_availability() -> None:
    """Database::drivers() in PHP inspects which extensions are actually
    loaded; the port returned a hardcoded literal list."""
    drivers = DB.drivers()
    assert "sqlite" in drivers
