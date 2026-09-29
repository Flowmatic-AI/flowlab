import threading
import time
from pathlib import Path

import pytest

db_module = pytest.importorskip("flowlab.modules.db.database")

from flowlab.modules.cache import Cache
from flowlab.modules.db.database import DB


def _cache() -> Cache:
    db = DB.connect_sqlite(":memory:")
    return Cache.connect_database(db, table="cache")


def test_set_get() -> None:
    cache = _cache()
    cache.set("foo", {"a": 1})

    assert cache.get("foo") == {"a": 1}
    assert cache.exists("foo") is True


def test_missing_key() -> None:
    cache = _cache()

    assert cache.get("missing") is None
    assert cache.exists("missing") is False


def test_overwrite() -> None:
    cache = _cache()
    cache.set("foo", "bar")
    cache.set("foo", "baz")

    assert cache.get("foo") == "baz"


def test_delete() -> None:
    cache = _cache()
    cache.set("foo", "bar")
    cache.delete("foo")

    assert cache.get("foo") is None


def test_ttl_expiry() -> None:
    cache = _cache()
    cache.set("foo", "bar", ttl=0.01)

    assert cache.get("foo") == "bar"
    time.sleep(0.02)

    assert cache.get("foo") is None
    assert cache.exists("foo") is False


def test_clear() -> None:
    cache = _cache()
    cache.set("foo", "1")
    cache.set("bar", "2")
    cache.clear()

    assert cache.get("foo") is None
    assert cache.get("bar") is None


def test_add() -> None:
    cache = _cache()

    assert cache.add("foo", "1") is True
    assert cache.add("foo", "2") is False
    assert cache.get("foo") == "1"


def test_pull() -> None:
    cache = _cache()
    cache.set("foo", "bar")

    assert cache.pull("foo") == "bar"
    assert cache.get("foo") is None


def test_remember_computes_once() -> None:
    cache = _cache()
    calls = []

    def callback() -> str:
        calls.append(1)
        return "computed"

    assert cache.remember("foo", callback) == "computed"
    assert cache.remember("foo", callback) == "computed"
    assert len(calls) == 1


def test_increment_starts_a_counter_and_adds_to_it() -> None:
    cache = _cache()

    assert cache.increment("hits") == 1
    assert cache.increment("hits") == 2
    assert cache.increment("hits", 5) == 7
    assert cache.increment("hits", 0) == 7


def test_decrement() -> None:
    cache = _cache()
    cache.increment("stock", 10)

    assert cache.decrement("stock", 3) == 7


def test_increment_ttl_counts_from_the_first_increment() -> None:
    cache = _cache()
    cache.increment("hits", ttl=1)
    time.sleep(0.6)
    cache.increment("hits", ttl=1)
    time.sleep(0.6)

    assert cache.increment("hits", 0) == 0


def test_increment_loses_no_updates_across_connections(tmp_path: Path) -> None:
    path = str(tmp_path / "cache.sqlite")
    Cache.connect_database(DB.connect_sqlite(path))

    def work() -> None:
        cache = Cache.connect_database(DB.connect_sqlite(path))
        for _ in range(25):
            cache.increment("hits")

    threads = [threading.Thread(target=work) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert Cache.connect_database(DB.connect_sqlite(path)).increment("hits", 0) == 100
