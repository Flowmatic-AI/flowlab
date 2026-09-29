import time

import pytest

valkey = pytest.importorskip("valkey")

from flowlab.modules.cache import Cache


def _cache() -> Cache:
    try:
        client = valkey.Valkey(host="localhost", port=6380)
        client.ping()
    except valkey.exceptions.ValkeyError:
        pytest.skip("valkey is not reachable on localhost:6380 — run `docker compose up -d valkey`")

    cache = Cache.connect_valkey(host="localhost", port=6380)
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
    cache = _cache()
    cache.set("foo", "bar", ttl=0.1)

    assert cache.get("foo") == "bar"
    time.sleep(0.2)

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


def test_increment_ttl_counts_from_the_first_increment() -> None:
    cache = _cache()
    cache.increment("hits", ttl=1)
    time.sleep(0.6)
    cache.increment("hits", ttl=1)
    time.sleep(0.6)

    assert cache.increment("hits", 0) == 0
