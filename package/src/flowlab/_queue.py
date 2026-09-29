from flowlab._settings import QueueDriver, QueueSettings
from flowlab._state import get_app
from flowlab.modules.db import DB as Database
from flowlab.modules.queue import Queue


def connect_queue(settings: QueueSettings, db: Database) -> Queue:
    driver = settings.queue_driver
    options = settings.queue_options()

    if driver is QueueDriver.SYNC:
        return Queue.sync(settings.queue_name)

    if driver is QueueDriver.DATABASE:
        return Queue.connect_database(db, default=settings.queue_name, **options)

    if driver is QueueDriver.REDIS:
        return Queue.connect_redis(default=settings.queue_name, **options)

    if driver is QueueDriver.VALKEY:
        return Queue.connect_valkey(default=settings.queue_name, **options)

    if driver is QueueDriver.CLOUDTASKS:
        return Queue.connect_cloud_tasks(db, default=settings.queue_name, **options)

    raise ValueError(f"Unsupported QUEUE_DRIVER: {driver!r}")


def get_queue() -> Queue:
    return get_app().queue
