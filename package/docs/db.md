# flowlab.modules.db

A database abstraction with a fluent query builder and a small ORM.
SQLite works out of the box (`sqlite3` ships with Python); PostgreSQL and
MySQL/MariaDB need a driver.

```python
from flowlab.modules.db.database import DB
```

## Connecting

```python
db = DB.connect_sqlite(":memory:")  # or a file path
db = DB.connect_postgresql("mydb", host="localhost", port=5432, user="postgres", password="secret")
db = DB.connect_mysql("mydb", host="localhost", user="root", password="secret")
db = DB.connect_mariadb("mydb", host="localhost", user="root", password="secret")  # MySQL with the MariaDB dialect
```

PostgreSQL uses asyncpg by default (install the `asyncpg` extra); pass
`asyncpg_adapter=False` to use psycopg instead. Both behave identically through
the public API, which stays synchronous.

Arguments every `connect_*` accepts:

| Argument | Purpose |
|----------|---------|
| `startup_queries` | SQL run on every new connection, including after a reconnect |
| `options` | Driver and dialect options (e.g. `{"foreign_keys": False}` for SQLite, `{"sslmode": "require"}` for PostgreSQL) |
| `debug_callback` | `(query, starttime, error)` called per statement |
| `ensure_always_connected` | Run `reconnect_if_disconnected()` before every statement |
| `max_concurrent_connections` | Cap on live connections across all threads |
| `acquire_connection_timeout` | Seconds to wait for a connection slot before `ConnectionLimitError` |

SQLite enables foreign keys by default. `DB.drivers()` lists the drivers available.

## Query builder

```python
result = (
    db.select("users")
    .columns(["id", "name", "email"])
    .where_equals("active", True)
    .where_greater_than("age", 18)
    .order_by_asc("name")
    .limit(10)
    .execute()
)

rows = result.fetch_dicts()  # list of dicts
first = result.fetch_dict()  # one row or None
count = result.scalar()  # first column of first row

db.insert("users").values({"name": "Alice"}).execute()
db.insert("users").values({"name": "A"}, {"name": "B"}).execute()
db.update("users").updates({"name": "Alicia"}).where_equals("id", 1).execute()
db.delete("users").where_equals("id", 1).execute()

db.create_table("users").if_not_exists().identity("id").string("email", size=255, not_null=True).execute()
db.drop_table("users").if_exists().execute()

db.exec("CREATE INDEX ...")  # raw statement
db.query("SELECT ... WHERE x = ?", [1])  # raw query returning a result
```

The builder also supports joins, `group_by`, `having_*`, `distinct`, `order_by_asc/desc`,
`limit`/`offset`, unions, `RETURNING` and `ON CONFLICT` on inserts (native where the
database supports it, emulated otherwise), and `where_*` conditions
(`where_equals`, `where_greater_than`, `where_in`, `where_is_null`, ...).

Transactions:

```python
db.begin_transaction()
db.commit_transaction()  # or db.rollback_transaction()
db.transaction(lambda database: database.insert("users").values({"name": "C"}).execute())  # auto commit/rollback
```

Helpers, importable from `flowlab.modules.db`: `now()`, `current_timestamp()`, `raw()`,
`identifier()`, `alias()`, `sub_query()`, `expression()`, `PostgresArray`, `QueryWithParams`.

Schema introspection: `db.list_tables()`, `db.describe_table("users")`
(returns a `TableDescription` whose `create_table(db)` recreates it),
`db.copy_from()` / `db.copy_to()`.

Exceptions (all in `flowlab.modules.db`): `DatabaseError` is the base; `AdapterError`,
`DriverError`, `QueryError`, `QueryWithParamsError`, `ConnectionLimitError` and `ModelError`
derive from it.

## ORM

Declare models with `Model`; everything that acts on them goes through the DB.

```python
from __future__ import annotations

from flowlab.modules.db.orm import (
    AutoIncrement,
    BelongsTo,
    HasMany,
    Model,
    PrimaryKey,
    belongs_to,
    column,
    has_many,
)


class Post(Model):
    __table__ = "posts"
    id: AutoIncrement = None
    user_id: int | None = None
    title: str
    author: BelongsTo["User"] = belongs_to()


class User(Model):
    __table__ = "users"
    id: AutoIncrement = None
    name: str
    posts: HasMany[Post] = has_many()
```

`AutoIncrement` marks a database-filled integer key, `PrimaryKey[T]` a key you supply,
and `Annotated[str, column(column_name="db_name")]` maps to a differently named column.
Relations: `has_one`, `has_many`, `belongs_to`, `many_to_many("through_table")`; each takes
`foreign_key=` overrides.

```python
users = db.select_models(User).relation("posts").where_equals("name", "Alice").fetch_models()
user = db.select_models(User).where_equals("id", 1).fetch_model()

alice = User(name="Alice", posts=[Post(title="First")])
db.insert_models([alice]).relation("posts").execute()  # ids are written back onto the models
db.update_models([alice]).columns(["name"]).execute()
db.delete_models([alice]).execute()
```

Each relation is loaded with one batched `IN` query, never a join. `model_mapper(Model)`
returns the `ModelMapper` (`to_model`, `to_row`, ...), and `model_meta(Model)` the column and
relation metadata.

## Migrations

Migrations live in their own module, `flowlab.modules.migrator`. See [migrator.md](migrator.md).
