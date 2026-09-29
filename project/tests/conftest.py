import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_database = Path(tempfile.mkdtemp()) / "test.sqlite"

os.environ.update(
    APP_ENV="local",
    JWT_SECRET="test-suite-secret-at-least-32-bytes-long",
    DB_DRIVER="sqlite",
    DB_NAME=str(_database),
    CACHE_DRIVER="memory",
    QUEUE_DRIVER="sync",  # jobs run as they are dispatched, like Laravel's phpunit.xml
    AUTH_RATE_LIMIT="none",  # the whole suite registers and logs in from one client address
)

import main  # noqa: E402

with main.app.lifespan():
    main.app.migrator.up()


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(main.app) as test_client:
        yield test_client
