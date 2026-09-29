import shutil
from collections.abc import Collection, Mapping
from pathlib import Path

from flowlab.modules.db.database import DB as Database
from flowlab.modules.migrator._migrator import Migrator


class ForeignKeyCycle(ValueError):
    def __init__(self, tables: Collection[str]) -> None:
        super().__init__(f"tables reference each other in a cycle: {', '.join(sorted(tables))}")


def drop_order(references: Mapping[str, Collection[str]]) -> list[str]:
    remaining = {table: set(targets) & references.keys() - {table} for table, targets in references.items()}
    order: list[str] = []

    while remaining:
        referenced = set().union(*remaining.values())
        droppable = sorted(table for table in remaining if table not in referenced)

        if not droppable:
            raise ForeignKeyCycle(remaining)

        order.extend(droppable)

        for table in droppable:
            del remaining[table]

    return order


def migrator(db: Database, directory: Path) -> Migrator:
    directory.mkdir(parents=True, exist_ok=True)
    migrator = Migrator(db, directory)
    migrator.init()

    return migrator


def drop_all_tables(db: Database) -> list[str]:
    references = {
        table: {foreign_key.ref_table for foreign_key in db.describe_table(table).constraints.foreign_keys}
        for table in db.list_tables()
    }
    tables = drop_order(references)

    for table in tables:
        db.drop_table(table).execute()

    return tables


def scaffold(db: Database, directory: Path, name: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    path: str = Migrator(db, directory).create(name)

    return path


def publish_migrations(source: Path, target: Path) -> list[Path]:
    """Copy each migration in ``source`` that ``target`` does not have yet, by filename."""
    target.mkdir(parents=True, exist_ok=True)
    published = []

    for template in sorted(source.glob("*.py")):
        if template.name.startswith("_") or (target / template.name).exists():
            continue

        published.append(Path(shutil.copyfile(template, target / template.name)))

    return published
