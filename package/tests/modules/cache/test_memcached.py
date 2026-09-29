import time

import pytest

pymemcache = pytest.importorskip("pymemcache")

from flowlab.modules.cache import Cache


def _cache() -> Cache:
    from pymemcache.client.base import Client

    try:
        client = Client(("localhost", 11211), connect_timeout=1, timeout=1)
        client.version()
    except OSError:
        pytest.skip("memcached is not reachable on localhost:11211 — run `docker compose up -d memcached`")

    cache = Cache.connect_memcached(host="localhost", port=11211)
    cache.clear()
    return cache


def test_set_get() -> None:
    cache = _cache()
    cache.set("foo", {"a": 1})

    assert cache.get("foo") == {"a": 1}
    assert cache.exists("foo") is True


def test_missing_key() -> None:
    cache = _cache()

    assert cache.get("missing") is None
    assert cache.exists("missing") is False


def test_delete() -> None:
    cache = _cache()
    cache.set("foo", "bar")
    cache.delete("foo")

    assert cache.get("foo") is None


def test_ttl_expiry() -> None:
    # Memcached's expiration is second-granularity, unlike Redis/Valkey's millisecond
    # precision, so this needs a full second rather than the 0.1s used elsewhere.
    cache = _cache()
    cache.set("foo", "bar", ttl=1)

    assert cache.get("foo") == "bar"
    time.sleep(1.2)

    assert cache.get("foo") is None


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


def test_increment_ttl_expires_the_counter() -> None:
    # Memcached expiry has whole-second granularity, so only check that the counter goes away.
    cache = _cache()
    cache.increment("hits", ttl=1)
    time.sleep(2.1)

    assert cache.increment("hits", 0) == 0


def test_decrement_stops_at_zero() -> None:
    cache = _cache()
    cache.increment("stock", 2)

    assert cache.decrement("stock", 5) == 0
