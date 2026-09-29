from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flowlab.modules.db import DatabaseError
from flowlab.modules.migrator._loader import discover_migration_files, load_migration
from flowlab.modules.migrator._template import render_migration

if TYPE_CHECKING:
    from flowlab.modules.db.database import DB
    from flowlab.modules.migrator._migration_abc import MigrationABC


class Migrator:
    def __init__(
        self,
        db: DB,
        migrations_dir: str | os.PathLike[str],
        migrations_table: str = "migrations",
    ) -> None:
        self._db = db
        self._migrations_dir = os.fspath(migrations_dir)
        self._migrations_table = migrations_table

    def init(self) -> None:
        self._db.create_table(self._migrations_table).if_not_exists().identity("id").string(
            "filename", size=255, not_null=True
        ).integer("batch", not_null=True).datetime("applied_at", not_null=True).execute()

    def up(self) -> None:
        rows = self._db.select(self._migrations_table).columns(["filename"]).execute().fetch_dicts()
        applied = {row["filename"] for row in rows}

        pending = [f for f in discover_migration_files(self._migrations_dir) if f not in applied]
        if not pending:
            return

        batch = self._current_batch() + 1

        for filename in pending:
            migration = load_migration(self._migrations_dir, filename)

            def action(db: DB, migration: MigrationABC = migration, filename: str = filename) -> None:
                migration.up(db)
                self._insert_record(filename, batch)

            self._run(migration, action)

    def down(self) -> None:
        batch = self._current_batch()
        if batch == 0:
            return

        rows = (
            self._db.select(self._migrations_table)
            .columns(["filename"])
            .where_equals("batch", batch)
            .execute()
            .fetch_dicts()
        )
        filenames = sorted((row["filename"] for row in rows), reverse=True)
        available = set(discover_migration_files(self._migrations_dir))

        for filename in filenames:
            if filename not in available:
                raise DatabaseError(f"Migration file not found: {os.path.join(self._migrations_dir, filename)}")
            migration = load_migration(self._migrations_dir, filename)

            def action(db: DB, migration: MigrationABC = migration, filename: str = filename) -> None:
                migration.down(db)
                self._db.delete(self._migrations_table).where_equals("filename", filename).execute()

            self._run(migration, action)

    def create(self, name: str) -> str:
        now = datetime.now(UTC).astimezone()
        filename = f"{now.strftime('%Y%m%d%H%M%S')}_{name}.py"

        os.makedirs(self._migrations_dir, exist_ok=True)

        path = os.path.join(self._migrations_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_migration(name))

        return path

    def _current_batch(self) -> int:
        result = self._db.select(self._migrations_table).columns(["batch"]).order_by_desc("batch").limit(1).execute()
        row = result.fetch_dict()
        return int(row["batch"]) if row else 0

    def _insert_record(self, filename: str, batch: int) -> None:
        self._db.insert(self._migrations_table).values(
            {
                "filename": filename,
                "batch": batch,
                "applied_at": datetime.now(UTC).astimezone(),
            }
        ).execute()

    def _run(self, migration: MigrationABC, action: Callable[[DB], None]) -> None:
        if migration.in_transaction():
            self._db.transaction(action)
        else:
            action(self._db)
