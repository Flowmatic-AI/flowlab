from flowlab._exceptions import SchemaMismatch
from flowlab._settings import QueueDriver
from flowlab._state import get_app
from flowlab.modules.db import DB as Database

TABLES = {
    "jobs": ("id", "uuid", "queue", "payload", "attempts", "reservation", "available_at", "created_at"),
    "failed_jobs": ("id", "uuid", "queue", "payload", "exception", "failed_at"),
}


# Cloud Tasks holds the waiting jobs itself; only the failed ones are kept in the database.
DRIVER_TABLES = {
    QueueDriver.DATABASE: ("jobs", "failed_jobs"),
    QueueDriver.CLOUDTASKS: ("failed_jobs",),
}


def check_schema(db: Database) -> None:
    needed = DRIVER_TABLES.get(get_app().queue_settings.queue_driver, ())

    if not needed:
        return

    tables = set(db.list_tables())
    missing: list[str] = []

    for table in needed:
        if table not in tables:
            missing.append(f"table {table}")
            continue

        columns = {column.name for column in db.describe_table(table).columns}
        missing.extend(f"column {table}.{column}" for column in TABLES[table] if column not in columns)

    if missing:
        raise SchemaMismatch("queue", missing)
