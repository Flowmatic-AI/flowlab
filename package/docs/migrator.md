# flowlab.modules.migrator

One migration is one file containing exactly one `MigrationABC` subclass:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from flowlab.modules.migrator import MigrationABC

if TYPE_CHECKING:
    from flowlab.modules.db.database import DB


class CreateUsersTable(MigrationABC):
    def up(self, db: DB) -> None:
        db.create_table("users").if_not_exists().identity("id").string("email", size=255).execute()

    def down(self, db: DB) -> None:
        db.drop_table("users").if_exists().execute()
```

```python
from flowlab.modules.migrator import Migrator

migrator = Migrator(db, "app/migrations")  # migrations_table="migrations"
migrator.init()  # create the bookkeeping table (idempotent)
migrator.up()  # apply all pending files as one batch
migrator.down()  # roll back the latest batch
path = migrator.create("add_email_to_users")  # write <YYYYMMDDHHMMSS>_<name>.py
```

Rules: run `init()` first; files apply in filename order; files starting with `_` are
skipped; each migration runs in a transaction unless `in_transaction()` returns `False`;
zero or several `MigrationABC` subclasses in one file raise `DatabaseError`; `down()` reverses a
whole batch, in reverse filename order.

`migrations_dir` is a `str` or a path, and must exist when `up()` or `down()` runs.

## Publishing templates

`publish_migrations(source, target)` copies each `.py` file in `source` that
`target` has no file of the same name for, and returns the new paths. Files
starting with `_` are skipped, and existing files are never overwritten. Modules
use it to hand their migrations to the project (see `auth:install`).

## Schema helpers

`drop_all_tables(db)` drops every table, children before parents, using the
foreign keys from `db.describe_table()`. `drop_order(references)` is the pure
ordering it uses; it raises `ForeignKeyCycle` when tables reference each other.

## In a FlowLab app

The app runs one `Migrator` over the project's `migrations/` folder, and only
that folder:
`migrations:init`, `migrations:up`, `migrations:down`, `migrations:fresh [--force]`
and `migrations:make <name>` (writes to the project's `migrations/`).
