from flowlab._exceptions import SchemaMismatch
from flowlab._settings import QueueDriver
from flowlab._state import get_app
from flowlab.modules.db.database import DB as Database

TABLES = {
    "jobs": ("id", "uuid", "queue", "payload", "attempts", "reservation", "available_at", "created_at"),
    "failed_jobs": ("id", "uuid", "queue", "payload", "exception", "failed_at"),
}


def check_schema(db: Database) -> None:
    if get_app().queue_settings.queue_driver is not QueueDriver.DATABASE:
        return

    tables = set(db.list_tables())
    missing: list[str] = []

    for table, required in TABLES.items():
        if table not in tables:
            missing.append(f"table {table}")
            continue

        columns = {column.name for column in db.describe_table(table).columns}
        missing.extend(f"column {table}.{column}" for column in required if column not in columns)

    if missing:
        raise SchemaMismatch("queue", missing)
