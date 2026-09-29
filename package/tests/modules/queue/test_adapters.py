import functools
import importlib
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from flowlab.modules.db import DB
from flowlab.modules.migrator import publish_migrations
from flowlab.modules.migrator._schema import migrator
from flowlab.modules.queue import MIGRATIONS_DIR, Queue
from flowlab.modules.queue.adapters import DatabaseAdapter, RedisLikeAdapter

MakeQueue = Callable[..., Queue]


def _database(tmp_path: Path) -> MakeQueue:
    publish_migrations(MIGRATIONS_DIR, tmp_path / "migrations")
    path = str(tmp_path / "queue.sqlite")
    migrator(DB.connect_sqlite(path), tmp_path / "migrations").up()

    return lambda retry_after=90: Queue(DatabaseAdapter(DB.connect_sqlite(path), retry_after))


def _fakeredis(tmp_path: Path) -> MakeQueue:
    fakeredis = pytest.importorskip("fakeredis")
    pytest.importorskip("lupa", reason="fakeredis needs lupa to run Lua scripts")
    server = fakeredis.FakeServer()

    return lambda retry_after=90: Queue(RedisLikeAdapter(fakeredis.FakeRedis(server=server), retry_after))


@functools.cache
def _reachable(module: str, port: int) -> bool:
    client_module = importlib.import_module(module)
    client_class = client_module.Redis if module == "redis" else client_module.Valkey

    try:
        client_class(host="localhost", port=port, socket_connect_timeout=0.5).ping()
    except client_module.exceptions.ConnectionError:
        return False

    return True


def _server(module: str, port: int) -> Callable[[Path], MakeQueue]:
    def make(tmp_path: Path) -> MakeQueue:
        client_module = pytest.importorskip(module)
        client_class = client_module.Redis if module == "redis" else client_module.Valkey

        if not _reachable(module, port):
            pytest.skip(f"{module} is not reachable on localhost:{port}")

        client = client_class(host="localhost", port=port)
        client.flushdb()
        return lambda retry_after=90: Queue(RedisLikeAdapter(client_class(host="localhost", port=port), retry_after))

    return make


@pytest.fixture(params=["database", "fakeredis", "redis", "valkey"])
def make_queue(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[MakeQueue]:
    factories = {
        "database": _database,
        "fakeredis": _fakeredis,
        "redis": _server("redis", 6379),
        "valkey": _server("valkey", 6380),
    }
    yield factories[request.param](tmp_path)


def test_push_pop_delete(make_queue: MakeQueue) -> None:
    queue = make_queue()
    id = queue.push("app.jobs:send", [1], {"to": "ada"})

    job = queue.pop()

    assert job is not None
    assert (job.id, job.queue, job.attempts) == (id, "default", 1)
    assert '"to": "ada"' in job.payload
    assert queue.size() == 1
    assert queue.pop() is None

    queue.delete(job)

    assert queue.size() == 0


def test_jobs_come_out_first_in_first_out(make_queue: MakeQueue) -> None:
    queue = make_queue()
    ids = [queue.push("app.jobs:send", [n]) for n in range(3)]

    assert [job.id for job in iter(queue.pop, None)] == ids


def test_queues_are_separate_and_popped_in_priority_order(make_queue: MakeQueue) -> None:
    queue = make_queue()
    low = queue.push("app.jobs:send", queue="low")
    high = queue.push("app.jobs:send", queue="high")

    first, second = queue.pop("high", "low"), queue.pop("high", "low")

    assert first is not None and second is not None
    assert (first.id, first.queue, second.id) == (high, "high", low)
    assert queue.pop() is None


def test_delayed_jobs_wait(make_queue: MakeQueue) -> None:
    queue = make_queue()
    queue.push("app.jobs:send", delay=0.3)

    assert queue.pop() is None
    assert queue.size() == 1

    time.sleep(0.4)

    assert queue.pop() is not None


def test_release_puts_a_job_back_and_counts_the_attempt(make_queue: MakeQueue) -> None:
    queue = make_queue()
    id = queue.push("app.jobs:send")
    job = queue.pop()
    assert job is not None

    queue.release(job, delay=0.3)

    assert queue.pop() is None
    time.sleep(0.4)
    again = queue.pop()
    assert again is not None
    assert (again.id, again.attempts) == (id, 2)


def test_a_job_whose_reservation_ran_out_is_handed_out_again(make_queue: MakeQueue) -> None:
    queue = make_queue(retry_after=0.3)
    id = queue.push("app.jobs:send")
    crashed = queue.pop()
    assert crashed is not None

    assert queue.pop() is None
    time.sleep(0.4)
    again = queue.pop()

    assert again is not None
    assert (again.id, again.attempts) == (id, 2)

    queue.delete(crashed)
    assert queue.size() == 1, "the first worker's late delete must not remove the job the second worker holds"

    queue.delete(again)
    assert queue.size() == 0


def test_failed_jobs_are_kept_retried_forgotten_and_flushed(make_queue: MakeQueue) -> None:
    queue = make_queue()
    first, second = queue.push("app.jobs:send", [1]), queue.push("app.jobs:send", [2], queue="emails")

    for job in iter(lambda: queue.pop("default", "emails"), None):
        queue.fail(job, f"Traceback...\nRuntimeError: {job.id}")

    assert queue.size() == 0
    assert [job.id for job in queue.failed()] == [second, first]
    failed = queue.find_failed(second)
    assert failed is not None
    assert (failed.queue, failed.exception.splitlines()[-1]) == ("emails", f"RuntimeError: {second}")

    assert queue.retry(second) is True
    assert queue.retry("nope") is False
    retried = queue.pop("emails")
    assert retried is not None
    assert (retried.id, retried.attempts) == (second, 1)

    assert queue.forget(first) is True
    assert queue.forget(first) is False
    assert queue.failed() == []

    queue.fail(retried, "again")
    assert queue.flush() == 1
    assert queue.failed() == []


def test_clear_deletes_waiting_delayed_and_reserved_jobs(make_queue: MakeQueue) -> None:
    queue = make_queue()
    queue.push("app.jobs:send")
    queue.push("app.jobs:send", delay=60)
    queue.push("app.jobs:send")
    queue.push("app.jobs:send", queue="other")
    queue.pop()

    assert queue.clear() == 3
    assert queue.size() == 0
    assert queue.size("other") == 1


def test_concurrent_workers_never_get_the_same_job(make_queue: MakeQueue) -> None:
    ids = {make_queue().push("app.jobs:send", [n]) for n in range(40)}
    taken: list[str] = []
    lock = threading.Lock()

    def work() -> None:
        queue = make_queue()

        for job in iter(queue.pop, None):
            with lock:
                taken.append(job.id)

            queue.delete(job)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(taken) == sorted(ids)
