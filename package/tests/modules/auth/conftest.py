import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from flowlab import FlowLab
from flowlab._settings import AuthSettings, DatabaseSettings, FastAPISettings, FastMCPSettings, TyperSettings
from flowlab.modules.auth import MIGRATIONS_DIR
from flowlab.modules.db.database import DB
from flowlab.modules.migrator import publish_migrations

JWT_SECRET = "test-suite-secret-at-least-32-bytes-long"

USERS_MIGRATION = """from flowlab.modules.migrator import MigrationABC


class CreateUsersTable(MigrationABC):
    def up(self, db):
        db.create_table("users")\\
            .auto_increment("id")\\
            .string("email", not_null=True)\\
            .string("password", not_null=True)\\
{extra}            .current_timestamp("created_at", not_null=True)\\
            .current_timestamp("updated_at", not_null=True)\\
            .datetime("deleted_at")\\
            .unique_constraint(["email"])\\
            .execute()

    def down(self, db):
        db.drop_table("users").execute()
"""


def write_users_migration(project_dir: Path, extra: str = "") -> None:
    """Write a users migration with extra columns, then publish the other auth migrations next to it."""
    migrations = project_dir / "migrations"
    migrations.mkdir(exist_ok=True)
    (migrations / "0001_01_01_000000_create_users_table.py").write_text(USERS_MIGRATION.format(extra=extra))
    publish_migrations(MIGRATIONS_DIR, migrations)


@pytest.fixture()
def app(tmp_path: Path) -> Iterator[FlowLab]:
    publish_migrations(MIGRATIONS_DIR, tmp_path / "migrations")

    flowlab = FlowLab(
        FastAPISettings(),
        FastMCPSettings(),
        TyperSettings(),
        database_settings=DatabaseSettings(db_driver="sqlite", db_name=str(tmp_path / "test.sqlite")),
        auth_settings=AuthSettings(jwt_secret=JWT_SECRET),
        project_dir=tmp_path,
    )

    with flowlab.lifespan():
        flowlab.migrator.up()

    yield flowlab


@pytest.fixture()
def client(app: FlowLab) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(app: FlowLab, client: TestClient) -> DB:
    return app.db


@pytest.fixture()
def users_migration() -> Callable[[Path, str], None]:
    return write_users_migration


@pytest.fixture()
def jwt_secret() -> str:
    return JWT_SECRET


@pytest.fixture()
def random_email() -> str:
    return f"user-{uuid.uuid4().hex}@example.com"
