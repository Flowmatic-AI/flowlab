from collections.abc import Generator
from typing import Annotated

from fastapi import Depends

from flowlab._settings import CacheDriver, CacheSettings
from flowlab._state import get_app
from flowlab.modules.cache import Cache as CacheStore
from flowlab.modules.db.database import DB as Database


def connect_cache_store(settings: CacheSettings, db: Database) -> CacheStore:
    driver = settings.cache_driver
    options = settings.cache_options()

    if driver is CacheDriver.MEMORY:
        return CacheStore.shared_memory()

    if driver is CacheDriver.DATABASE:
        return CacheStore.connect_database(db, **options)

    if driver is CacheDriver.REDIS:
        return CacheStore.connect_redis(**options)

    if driver is CacheDriver.VALKEY:
        return CacheStore.connect_valkey(**options)

    if driver is CacheDriver.MEMCACHED:
        return CacheStore.connect_memcached(**options)

    raise ValueError(f"Unsupported CACHE_DRIVER: {driver!r}")


def get_cache() -> CacheStore:
    return get_app().cache


def connect_cache() -> Generator[CacheStore, None, None]:
    yield get_cache()


Cache = Annotated[CacheStore, Depends(connect_cache)]
