"""Regression tests for PHP -> Python hand-port bugs in the core Query /
DML query-builder classes (work unit E).

Each test targets a specific behavioral mistranslation found by comparing
Database/Queries/Query.php, SelectQuery.php, InsertQuery.php, UpdateQuery.php,
DeleteQuery.php and their Traits/Objects against
src/flowlab/modules/db/query/_query.py, _select.py, _insert.py, _update.py,
_delete.py, _simple_mixins.py.
"""

from __future__ import annotations

from typing import Any

from flowlab.modules.db import DB
from flowlab.modules.db.dialects import SQLDialect
from flowlab.modules.db.query import InsertQuery, SelectQuery, UpdateQuery


def _fresh_db() -> DB:
    return DB.connect_sqlite(":memory:")


def test_explain_does_not_raise_nameerror(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.columns(["id"])

    class _FakeResult:
        def fetch_dicts(self) -> list[dict[str, Any]]:
            return [{"id": 1}]

    class _FakeDB:
        def query_with_params(self, qwp: Any, emulate: bool = False) -> Any:
            assert qwp.query.startswith("EXPLAIN ")
            return _FakeResult()

    q._database = _FakeDB()
    assert q.explain() == [{"id": 1}]


def test_select_count_does_not_raise_nameerror() -> None:
    db = _fresh_db()
    db.create_table("widgets").if_not_exists().identity("id").string("name").execute()
    db.insert("widgets").values({"name": "a"}).execute()
    db.insert("widgets").values({"name": "b"}).execute()

    assert db.select("widgets").count() == 2


def test_limit_negative_clears_limit(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.limit(10)
    q.limit(-1)
    qwp = q.to_query_with_params()
    assert "LIMIT" not in qwp.query


def test_offset_non_positive_clears_offset(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.offset(5)
    q.offset(0)
    qwp = q.to_query_with_params()
    assert "OFFSET" not in qwp.query

    q2 = SelectQuery(sql_dialect, "users", database=mock_db)
    q2.offset(-5)
    qwp2 = q2.to_query_with_params()
    assert "OFFSET" not in qwp2.query


def test_updates_replaces_rather_than_merges(sql_dialect: SQLDialect, mock_db) -> None:
    q = UpdateQuery(sql_dialect, "users", database=mock_db)
    q.updates({"name": "John", "age": 30})
    q.updates({"name": "Jane"})
    qwp = q.to_query_with_params()
    assert '"age"' not in qwp.query
    assert qwp.params == ["Jane"]


def test_returning_default_arg_means_all_columns(sql_dialect: SQLDialect, mock_db) -> None:
    q = UpdateQuery(sql_dialect, "users", database=mock_db)
    q.updates({"name": "John"})
    q.returning()
    assert q._returning_list == []
    assert q._returning_list is not None


def test_on_conflict_do_update_defaults_to_all_columns(sqlite_dialect) -> None:
    from flowlab.modules.db.database import DatabaseABC

    class _MockDB(DatabaseABC):
        def __init__(self) -> None:
            pass

    q = InsertQuery(sqlite_dialect, "users", database=_MockDB())
    q.values({"id": 1, "name": "John"})
    q.on_conflict_do_update(["id"])
    qwp = q.to_query_with_params()
    assert "DO UPDATE SET" in qwp.query
    assert "EXCLUDED" in qwp.query


def test_on_conflict_aliases(sql_dialect: SQLDialect, mock_db) -> None:
    q1 = InsertQuery(sql_dialect, "users", database=mock_db)
    q1.values({"id": 1})
    q1.insert_ignore(["id"])
    assert q1._on_conflict is not None and q1._on_conflict.updates is None

    q2 = InsertQuery(sql_dialect, "users", database=mock_db)
    q2.values({"id": 1, "name": "a"})
    q2.on_duplicate_key_update(["id"], {"name": "a"})
    assert q2._on_conflict is not None and q2._on_conflict.updates == {"name": "a"}


def test_columns_dict_keys_produce_aliases(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.columns({"user_name": "name", "id": "id"})
    qwp = q.to_query_with_params()
    assert '"name" AS "user_name"' in qwp.query
    assert '"id" AS "id"' in qwp.query


def test_columns_list_is_left_untouched(sql_dialect: SQLDialect, mock_db) -> None:
    q = SelectQuery(sql_dialect, "users", database=mock_db)
    q.columns(["id", "name"])
    qwp = q.to_query_with_params()
    assert qwp.query == 'SELECT "id", "name" FROM "users"'


def test_insert_into_renames_table(sql_dialect: SQLDialect, mock_db) -> None:
    q = InsertQuery(sql_dialect, "users", database=mock_db)
    q.into("other_table")
    q.values({"id": 1})
    qwp = q.to_query_with_params()
    assert '"other_table"' in qwp.query


def test_emulate_on_conflict_hides_on_conflict_from_dialect(sql_dialect: SQLDialect, mock_db) -> None:
    q = InsertQuery(sql_dialect, "users", database=mock_db)
    q.values({"id": 1, "name": "a"})
    q.on_conflict_do_nothing(["id"])
    q.emulate_on_conflict("id")
    qwp = q.to_query_with_params()
    assert "ON CONFLICT" not in qwp.query


def test_emulate_returning_hides_returning_from_dialect(sql_dialect: SQLDialect, mock_db) -> None:
    q = InsertQuery(sql_dialect, "users", database=mock_db)
    q.values({"name": "a"})
    q.returning(["id"])
    q.emulate_returning("id")
    qwp = q.to_query_with_params()
    assert "RETURNING" not in qwp.query


def test_emulated_on_conflict_do_update_upserts_existing_row() -> None:
    db = _fresh_db()
    db.create_table("users").if_not_exists().identity("id").string("name").string("email").execute()

    db.insert("users").values({"name": "a", "email": "a@x.com"}).execute()
    first_id = db.select("users").execute().fetch_dict()["id"]

    result = (
        db.insert("users")
        .values({"id": first_id, "name": "a", "email": "new@x.com"})
        .on_conflict_do_update(["id"])
        .emulate_on_conflict("id")
        .execute()
    )
    assert result is not None

    rows = db.select("users").execute().fetch_dicts()
    assert len(rows) == 1
    assert rows[0]["email"] == "new@x.com"


def test_emulated_on_conflict_do_nothing_ignores_existing_row() -> None:
    db = _fresh_db()
    db.create_table("users").if_not_exists().identity("id").string("name").string("email").execute()

    db.insert("users").values({"name": "a", "email": "a@x.com"}).execute()
    first_id = db.select("users").execute().fetch_dict()["id"]

    db.insert("users").values({"id": first_id, "name": "a", "email": "ignored@x.com"}).on_conflict_do_nothing(
        ["id"]
    ).emulate_on_conflict("id").execute()

    rows = db.select("users").execute().fetch_dicts()
    assert len(rows) == 1
    assert rows[0]["email"] == "a@x.com"


def test_emulated_on_conflict_inserts_when_no_row_matches() -> None:
    db = _fresh_db()
    db.create_table("users").if_not_exists().identity("id").string("name").string("email").execute()

    db.insert("users").values({"id": 999, "name": "new", "email": "new@x.com"}).on_conflict_do_update(
        ["id"]
    ).emulate_on_conflict("id").execute()

    rows = db.select("users").execute().fetch_dicts()
    assert len(rows) == 1
    assert rows[0]["name"] == "new"
