from __future__ import annotations

from pathlib import Path

import pytest

from flowlab.modules.db import DatabaseError
from flowlab.modules.db.database import DB
from flowlab.modules.migrator import Migrator

_TEMPLATE = """from flowlab.modules.migrator import MigrationABC


class {cls}(MigrationABC):
    def up(self, db):
        db.exec("CREATE TABLE {table} (id INTEGER)")

    def down(self, db):
        db.exec("DROP TABLE {table}")
"""


def _write(directory: Path, filename: str, table: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    cls = "M" + table
    (directory / filename).write_text(_TEMPLATE.format(cls=cls, table=table))


def _tables(db: DB) -> list[str]:
    rows = db.query("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'").fetch_dicts()
    return sorted(row["name"] for row in rows if row["name"] != "migrations")


@pytest.fixture
def db() -> DB:
    return DB.connect_sqlite(":memory:")


def test_up_applies_in_filename_order_and_down_rolls_back_the_batch(db: DB, tmp_path: Path) -> None:
    _write(tmp_path, "002_b.py", "b")
    _write(tmp_path, "001_a.py", "a")
    migrator = Migrator(db, tmp_path)
    migrator.init()

    migrator.up()

    rows = db.select("migrations").columns(["filename"]).order_by_asc("id").execute().fetch_dicts()
    assert [r["filename"] for r in rows] == ["001_a.py", "002_b.py"]
    assert _tables(db) == ["a", "b"]

    migrator.down()
    assert _tables(db) == []


def test_a_string_directory_works_too(db: DB, tmp_path: Path) -> None:
    _write(tmp_path, "001_a.py", "a")
    migrator = Migrator(db, str(tmp_path))
    migrator.init()

    migrator.up()

    assert _tables(db) == ["a"]


def test_a_missing_directory_raises(db: DB, tmp_path: Path) -> None:
    migrator = Migrator(db, tmp_path / "nope")
    migrator.init()

    with pytest.raises(DatabaseError):
        migrator.up()


def test_down_raises_when_an_applied_file_is_gone(db: DB, tmp_path: Path) -> None:
    _write(tmp_path, "001_a.py", "a")
    migrator = Migrator(db, tmp_path)
    migrator.init()
    migrator.up()
    (tmp_path / "001_a.py").unlink()

    with pytest.raises(DatabaseError, match="001_a.py"):
        migrator.down()


def test_create_writes_into_the_directory(db: DB, tmp_path: Path) -> None:
    path = Path(Migrator(db, tmp_path / "migrations").create("add users"))

    assert path.parent == tmp_path / "migrations"
    assert path.exists()


def test_publish_copies_only_the_missing_templates(tmp_path: Path) -> None:
    from flowlab.modules.migrator import publish_migrations

    templates, project = tmp_path / "templates", tmp_path / "project"
    _write(templates, "001_a.py", "a")
    _write(templates, "002_b.py", "b")
    (templates / "_helpers.py").write_text("")
    _write(project, "001_a.py", "customised")

    published = publish_migrations(templates, project)

    assert [path.name for path in published] == ["002_b.py"]
    assert "customised" in (project / "001_a.py").read_text()
    assert publish_migrations(templates, project) == []


def test_a_new_migration_has_no_docstrings(db: DB, tmp_path: Path) -> None:
    source = Path(Migrator(db, tmp_path / "migrations").create("create posts table")).read_text()

    assert '"""' not in source
    assert "class CreatePostsTable(MigrationABC):" in source
    compile(source, "migration.py", "exec")
