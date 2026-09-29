import threading
import time

from flowlab.modules.cache import Cache


def test_set_get() -> None:
    cache = Cache.shared_memory()
    cache.set("foo", {"a": 1})

    assert cache.get("foo") == {"a": 1}
    assert cache.exists("foo") is True


def test_missing_key() -> None:
    cache = Cache.shared_memory()

    assert cache.get("missing") is None
    assert cache.exists("missing") is False


def test_delete() -> None:
    cache = Cache.shared_memory()
    cache.set("foo", "bar")
    cache.delete("foo")

    assert cache.get("foo") is None


def test_ttl_expiry() -> None:
    cache = Cache.shared_memory()
    cache.set("foo", "bar", ttl=0.01)

    assert cache.get("foo") == "bar"
    time.sleep(0.02)

    assert cache.get("foo") is None
    assert cache.exists("foo") is False


def test_clear() -> None:
    cache = Cache.shared_memory()
    cache.set("foo", "1")
    cache.set("bar", "2")
    cache.clear()

    assert cache.get("foo") is None
    assert cache.get("bar") is None


def test_add() -> None:
    cache = Cache.shared_memory()

    assert cache.add("foo", "1") is True
    assert cache.add("foo", "2") is False
    assert cache.get("foo") == "1"


def test_add_after_expiry() -> None:
    cache = Cache.shared_memory()
    cache.set("foo", "1", ttl=0.01)
    time.sleep(0.02)

    assert cache.add("foo", "2") is True
    assert cache.get("foo") == "2"


def test_pull() -> None:
    cache = Cache.shared_memory()
    cache.set("foo", "bar")

    assert cache.pull("foo") == "bar"
    assert cache.get("foo") is None


def test_pull_missing_returns_default() -> None:
    cache = Cache.shared_memory()

    assert cache.pull("missing", default="fallback") == "fallback"


def test_remember_computes_once() -> None:
    cache = Cache.shared_memory()
    calls = []

    def callback() -> str:
        calls.append(1)
        return "computed"

    assert cache.remember("foo", callback) == "computed"
    assert cache.remember("foo", callback) == "computed"
    assert len(calls) == 1


def test_remember_recomputes_after_expiry() -> None:
    cache = Cache.shared_memory()

    assert cache.remember("foo", lambda: "first", ttl=0.01) == "first"
    time.sleep(0.02)

    assert cache.remember("foo", lambda: "second", ttl=0.01) == "second"


def test_increment_starts_a_counter_and_adds_to_it() -> None:
    cache = Cache.shared_memory()

    assert cache.increment("hits") == 1
    assert cache.increment("hits") == 2
    assert cache.increment("hits", 5) == 7
    assert cache.increment("hits", 0) == 7


def test_decrement() -> None:
    cache = Cache.shared_memory()
    cache.increment("stock", 10)

    assert cache.decrement("stock", 3) == 7


def test_increment_ttl_counts_from_the_first_increment() -> None:
    cache = Cache.shared_memory()
    cache.increment("hits", ttl=1)
    time.sleep(0.6)
    cache.increment("hits", ttl=1)
    time.sleep(0.6)

    assert cache.increment("hits", 0) == 0


def test_increment_is_atomic_across_threads() -> None:
    cache = Cache.shared_memory()

    def work() -> None:
        for _ in range(200):
            cache.increment("hits")

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert cache.increment("hits", 0) == 1600
