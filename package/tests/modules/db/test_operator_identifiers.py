from __future__ import annotations

from flowlab.modules.db import PostgresArray, raw
from flowlab.modules.db.database import DB


def test_where_operator_escapes_the_identifier() -> None:
    db = DB.connect_sqlite(":memory:")
    qwp = db.select("rows").where_operator("tags", "@>", PostgresArray(["a"])).to_query_with_params()
    assert qwp.query == 'SELECT * FROM "rows" WHERE "tags" @> ?'


def test_where_operator_escapes_a_qualified_identifier() -> None:
    db = DB.connect_sqlite(":memory:")
    qwp = (
        db.select("rows")
        .where_operator(["rows", "count"], ">", 1)
        .or_where_operator("x", "<", 0)
        .to_query_with_params()
    )
    assert qwp.query == 'SELECT * FROM "rows" WHERE "rows"."count" > ? OR "x" < ?'
    assert qwp.params == [1, 0]


def test_where_operator_leaves_raw_sql_unescaped() -> None:
    db = DB.connect_sqlite(":memory:")
    qwp = db.select("rows").where_operator(raw("lower(name)"), "=", "a").to_query_with_params()
    assert qwp.query == 'SELECT * FROM "rows" WHERE lower(name) = ?'


def test_having_operator_escapes_the_identifier() -> None:
    db = DB.connect_sqlite(":memory:")
    qwp = (
        db.select("rows")
        .group_by(["name"])
        .having_operator("total", ">", 1)
        .or_having_operator(["rows", "total"], "<", 9)
        .to_query_with_params()
    )
    assert qwp.query == 'SELECT * FROM "rows" GROUP BY "name" HAVING "total" > ? OR "rows"."total" < ?'


def test_join_where_operator_escapes_the_identifier() -> None:
    db = DB.connect_sqlite(":memory:")
    qwp = (
        db.select("a")
        .left_join("b", lambda join: join.on(["a", "id"], ["b", "a_id"]).where_operator(["b", "n"], ">", 1))
        .to_query_with_params()
    )
    assert '"b"."n" > ?' in qwp.query
