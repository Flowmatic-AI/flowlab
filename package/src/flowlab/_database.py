import contextlib
import importlib
import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from flowlab._settings import DatabaseSettings, DBDriver
from flowlab._state import get_app
from flowlab.modules.db import DB as Database

DB_API_DRIVER_MODULES = ("psycopg", "mysql.connector")

ASYNCPG_INTEGRITY_ERROR = ("asyncpg.exceptions", "IntegrityConstraintViolationError")


def _integrity_errors() -> tuple[type[BaseException], ...]:
    errors: list[type[BaseException]] = [sqlite3.IntegrityError]

    for module_name in DB_API_DRIVER_MODULES:
        with contextlib.suppress(ImportError):
            errors.append(importlib.import_module(module_name).IntegrityError)

    module_name, attribute = ASYNCPG_INTEGRITY_ERROR

    with contextlib.suppress(ImportError, AttributeError):
        errors.append(getattr(importlib.import_module(module_name), attribute))

    return tuple(errors)


INTEGRITY_ERRORS = _integrity_errors()


def connect_database(settings: DatabaseSettings, project_dir: Path) -> Database:
    driver = settings.db_driver
    options = settings.db_options(project_dir)

    if driver is DBDriver.SQLITE:
        return Database.connect_sqlite(**options)

    if driver is DBDriver.POSTGRESQL:
        return Database.connect_postgresql(**options)

    if driver is DBDriver.MYSQL:
        return Database.connect_mysql(**options)

    if driver is DBDriver.MARIADB:
        return Database.connect_mariadb(**options)

    raise ValueError(f"Unsupported DB_DRIVER: {driver!r}")


def get_db() -> Database:
    return get_app().db


def connect() -> Generator[Database, None, None]:
    yield get_db()


DB = Annotated[Database, Depends(connect)]
