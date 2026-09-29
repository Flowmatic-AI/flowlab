from __future__ import annotations

import signal
import threading
import time
import traceback
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from types import FrameType

from flowlab.modules.queue._job import JobNotFound, decode
from flowlab.modules.queue._queue import Queue
from flowlab.modules.queue.adapters._base import ReservedJob


class Worker:
    """Takes jobs off ``queues`` (in priority order) and runs them, until stopped.

    A job that raises is released to be tried again after its ``backoff`` until it has been tried ``tries`` times,
    then moved to the failed jobs. SIGINT and SIGTERM let the current job finish before the worker stops.
    """

    def __init__(
        self,
        queue: Queue,
        queues: Sequence[str] = (),
        *,
        sleep: float = 3,
        max_jobs: int | None = None,
        stop_when_empty: bool = False,
        max_idle: float | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        self.queue = queue
        self.queues = tuple(queues) or (queue.default,)
        self.sleep = sleep
        self.max_jobs = max_jobs
        self.stop_when_empty = stop_when_empty
        self.max_idle = max_idle
        self.log = log
        self._stop = threading.Event()

    def run(self) -> int:
        """Work until stopped, ``max_jobs`` is reached, the queues have been empty for ``max_idle`` seconds or, with
        ``stop_when_empty``, the queues are empty. Returns the number of jobs processed."""
        processed = 0
        idle_since: float | None = None

        with self._stop_on_signals():
            while not self._stop.is_set():
                job = self.queue.pop(*self.queues)

                if job is None:
                    if self.stop_when_empty:
                        break

                    wait = self.sleep

                    if self.max_idle is not None:
                        if idle_since is None:
                            idle_since = time.monotonic()

                        remaining = self.max_idle - (time.monotonic() - idle_since)

                        if remaining <= 0:
                            break

                        wait = min(wait, remaining)

                    self._stop.wait(wait)
                    continue

                idle_since = None
                self.process(job)
                processed += 1

                if self.max_jobs is not None and processed >= self.max_jobs:
                    break

        return processed

    def stop(self) -> None:
        self._stop.set()

    def process(self, job: ReservedJob) -> bool:
        """Run one reserved job, then delete, release or fail it. Returns whether it succeeded."""
        started = time.perf_counter()

        try:
            definition, args, kwargs = decode(job.payload)
        except (JobNotFound, ValueError, KeyError, TypeError):
            self.queue.fail(job, traceback.format_exc())
            self._log("FAIL", job, started, "cannot load job")
            return False

        try:
            definition(*args, **kwargs)
        except Exception as error:  # noqa: BLE001 - a job may raise anything; it must not stop the worker
            if job.attempts < definition.tries:
                self.queue.release(job, definition.retry_delay(job.attempts))
                self._log("RETRY", job, started, f"{type(error).__name__}: {error}")
            else:
                self.queue.fail(job, traceback.format_exc())
                self._log("FAIL", job, started, f"{type(error).__name__}: {error}")

            return False

        self.queue.delete(job)
        self._log("DONE", job, started)
        return True

    def _log(self, status: str, job: ReservedJob, started: float, detail: str = "") -> None:
        elapsed = (time.perf_counter() - started) * 1000
        name = _job_name(job.payload)
        line = f"{datetime.now(UTC).astimezone():%Y-%m-%d %H:%M:%S} {status:<5} {name} [{job.id[:8]}] {elapsed:.0f}ms"
        self.log(f"{line} {detail}".rstrip())

    @contextmanager
    def _stop_on_signals(self) -> Iterator[None]:
        if threading.current_thread() is not threading.main_thread():
            yield
            return

        def handle(signum: int, frame: FrameType | None) -> None:
            self.stop()

        previous = {sig: signal.signal(sig, handle) for sig in (signal.SIGINT, signal.SIGTERM)}

        try:
            yield
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def _job_name(payload: str) -> str:
    import json

    try:
        return str(json.loads(payload)["job"])
    except (ValueError, KeyError, TypeError):
        return "?"
