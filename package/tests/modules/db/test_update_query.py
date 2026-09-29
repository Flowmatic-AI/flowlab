from __future__ import annotations

from flowlab.modules.db.dialects import SQLDialect
from flowlab.modules.db.query import UpdateQuery


def test_update_simple(sql_dialect: SQLDialect, mock_db) -> None:
    q: UpdateQuery = UpdateQuery(sql_dialect, "users", database=mock_db)
    q.updates({"name": "John"})
    qwp = q.to_query_with_params()
    assert "UPDATE" in qwp.query
    assert "SET" in qwp.query
    assert '"name"' in qwp.query


def test_update_with_where(sql_dialect: SQLDialect, mock_db) -> None:
    q: UpdateQuery = UpdateQuery(sql_dialect, "users", database=mock_db)
    q.updates({"name": "Jane"})
    q.where_equals("id", 1)
    qwp = q.to_query_with_params()
    assert "WHERE" in qwp.query
    assert "Jane" in qwp.params
    assert 1 in qwp.params
