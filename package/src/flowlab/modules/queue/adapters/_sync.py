from __future__ import annotations

from flowlab.modules.queue.adapters._base import AdapterABC, FailedJob, ReservedJob


class SyncAdapter(AdapterABC):
    """Runs each job the moment it is dispatched, in the dispatching process. Exceptions reach the caller, and
    ``tries``, ``backoff`` and ``delay`` are ignored. Meant for tests and local development."""

    def push(self, queue: str, id: str, payload: str, delay: float = 0) -> None:
        from flowlab.modules.queue._job import perform

        perform(payload)

    def pop(self, queue: str) -> ReservedJob | None:
        return None

    def delete(self, job: ReservedJob) -> None:
        pass

    def release(self, job: ReservedJob, delay: float = 0) -> None:
        pass

    def fail(self, job: ReservedJob, exception: str) -> None:
        pass

    def size(self, queue: str) -> int:
        return 0

    def clear(self, queue: str) -> int:
        return 0

    def failed(self) -> list[FailedJob]:
        return []

    def find_failed(self, id: str) -> FailedJob | None:
        return None

    def forget_failed(self, id: str) -> bool:
        return False

    def flush_failed(self) -> int:
        return 0
