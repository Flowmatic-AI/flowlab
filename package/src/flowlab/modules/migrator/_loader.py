from __future__ import annotations

import importlib.util
import os

from flowlab.modules.db import DatabaseError
from flowlab.modules.migrator._migration_abc import MigrationABC


def discover_migration_files(migrations_dir: str) -> list[str]:
    if not os.path.isdir(migrations_dir):
        raise DatabaseError(f"Migrations directory does not exist: {migrations_dir}")

    filenames = [
        entry
        for entry in os.listdir(migrations_dir)
        if entry.endswith(".py") and not entry.startswith("_") and os.path.isfile(os.path.join(migrations_dir, entry))
    ]

    return sorted(filenames)


def load_migration(migrations_dir: str, filename: str) -> MigrationABC:
    path = os.path.join(migrations_dir, filename)
    stem = os.path.splitext(filename)[0]
    module_name = f"flowlab_migration_{stem}"

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise DatabaseError(f"Could not load migration module from: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    migration_classes = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, MigrationABC)
        and obj is not MigrationABC
        and obj.__module__ == module.__name__
    ]

    if len(migration_classes) == 0:
        raise DatabaseError(f"No MigrationABC subclass found in migration module: {path}")

    if len(migration_classes) > 1:
        raise DatabaseError(f"Multiple MigrationABC subclasses found in migration module: {path}")

    migration_class = migration_classes[0]

    return migration_class()
