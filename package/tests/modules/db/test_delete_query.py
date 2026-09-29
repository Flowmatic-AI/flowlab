from __future__ import annotations

from flowlab.modules.db.dialects import SQLDialect
from flowlab.modules.db.query import DeleteQuery


def test_delete_simple(sql_dialect: SQLDialect, mock_db) -> None:
    q = DeleteQuery(sql_dialect, "users", database=mock_db)
    qwp = q.to_query_with_params()
    assert qwp.query == 'DELETE FROM "users"'


def test_delete_with_where(sql_dialect: SQLDialect, mock_db) -> None:
    q = DeleteQuery(sql_dialect, "users", database=mock_db)
    q.where_equals("id", 5)
    qwp = q.to_query_with_params()
    assert "WHERE" in qwp.query
    assert qwp.params == [5]
