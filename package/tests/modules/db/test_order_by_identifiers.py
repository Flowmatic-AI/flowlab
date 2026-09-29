from __future__ import annotations

from flowlab.modules.db import alias, expression, raw
from flowlab.modules.db.database import DB


def test_order_by_accepts_a_qualified_list_a_raw_fragment_and_an_expression() -> None:
    db = DB.connect_sqlite(":memory:")

    query = (
        db.select_table("posts", "p")
        .columns([["p", "id"]])
        .inner_join(alias("users", "u"), lambda j: j.on(["u", "id"], ["p", "user_id"]))
        .order_by_desc(["p", "created_at"])
        .order_by_asc(raw('coalesce("p"."published_at", "p"."created_at")'))
        .order_by_asc(expression('abs("p"."score" - ?)', [5]))
        .order_by_asc("id")
    )

    assert query.to_sql() == (
        'SELECT "p"."id" FROM "posts" AS "p" INNER JOIN "users" AS "u" ON "u"."id" = "p"."user_id" '
        'ORDER BY "p"."created_at" DESC, coalesce("p"."published_at", "p"."created_at") ASC, '
        'abs("p"."score" - 5) ASC, "id" ASC'
    )


def test_raw_values_of_every_scalar_type_render_as_valid_literals() -> None:
    import datetime
    import uuid

    db = DB.connect_sqlite(":memory:")
    key = uuid.UUID("12345678-1234-5678-1234-567812345678")

    query = (
        db.select("events")
        .columns(["id"])
        .where_raw("day >= ?", [datetime.date(2026, 9, 16)])
        .where_raw("at < ?", [datetime.time(8, 30)])
        .where_raw("key = ?", [key])
    )

    assert query.to_sql() == (
        "SELECT \"id\" FROM \"events\" WHERE day >= '2026-09-16' AND at < '08:30:00' "
        "AND key = '12345678-1234-5678-1234-567812345678'"
    )
