from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Self

from flowlab.modules.queue.adapters._base import AdapterABC, FailedJob, ReservedJob

if TYPE_CHECKING:
    from flowlab.modules.db import DB


class Queue:
    def __init__(self, adapter: AdapterABC, default: str = "default") -> None:
        self._adapter = adapter
        self.default = default

    @classmethod
    def sync(cls, default: str = "default") -> Self:
        from flowlab.modules.queue.adapters._sync import SyncAdapter

        return cls(SyncAdapter(), default)

    @classmethod
    def connect_database(cls, db: DB, retry_after: float = 90, default: str = "default") -> Self:
        from flowlab.modules.queue.adapters._database import DatabaseAdapter

        return cls(DatabaseAdapter(db, retry_after), default)

    @classmethod
    def connect_redis(
        cls,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        retry_after: float = 90,
        default: str = "default",
        **options: Any,
    ) -> Self:
        from flowlab.modules.queue.adapters._redis import RedisAdapter

        return cls(RedisAdapter(host, port, db, password, retry_after, **options), default)

    @classmethod
    def connect_valkey(
        cls,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        retry_after: float = 90,
        default: str = "default",
        **options: Any,
    ) -> Self:
        from flowlab.modules.queue.adapters._valkey import ValkeyAdapter

        return cls(ValkeyAdapter(host, port, db, password, retry_after, **options), default)

    def push(
        self,
        job: str,
        args: Sequence[Any] = (),
        kwargs: dict[str, Any] | None = None,
        *,
        queue: str | None = None,
        delay: float = 0,
    ) -> str:
        """Queue the job at import path ``job`` (``"package.module:function"``) and return its id."""
        id = uuid.uuid4().hex

        try:
            payload = json.dumps({"id": id, "job": job, "args": list(args), "kwargs": kwargs or {}})
        except TypeError as error:
            raise TypeError(f"Arguments for {job} must be JSON serializable: {error}") from None

        self._adapter.push(queue or self.default, id, payload, max(delay, 0))
        return id

    def pop(self, *queues: str) -> ReservedJob | None:
        """Reserve the next job, looking at ``queues`` in order (the default queue when none are given)."""
        for queue in queues or (self.default,):
            job = self._adapter.pop(queue)

            if job is not None:
                return job

        return None

    def delete(self, job: ReservedJob) -> None:
        self._adapter.delete(job)

    def release(self, job: ReservedJob, delay: float = 0) -> None:
        self._adapter.release(job, max(delay, 0))

    def fail(self, job: ReservedJob, exception: str) -> None:
        self._adapter.fail(job, exception)

    def size(self, queue: str | None = None) -> int:
        return self._adapter.size(queue or self.default)

    def clear(self, queue: str | None = None) -> int:
        """Delete every job on ``queue`` that has not finished, and return how many there were."""
        return self._adapter.clear(queue or self.default)

    def failed(self) -> list[FailedJob]:
        return self._adapter.failed()

    def find_failed(self, id: str) -> FailedJob | None:
        return self._adapter.find_failed(id)

    def retry(self, id: str) -> bool:
        """Put a failed job back on its queue, with its attempts counted from zero again."""
        failed = self._adapter.find_failed(id)

        if failed is None:
            return False

        self._adapter.push(failed.queue, failed.id, failed.payload)
        self._adapter.forget_failed(id)
        return True

    def forget(self, id: str) -> bool:
        return self._adapter.forget_failed(id)

    def flush(self) -> int:
        """Delete every failed job, and return how many there were."""
        return self._adapter.flush_failed()

    def close(self) -> None:
        self._adapter.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
