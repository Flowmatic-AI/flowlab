from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ReservedJob:
    """A job a worker has taken off the queue. Nobody else gets it until it is deleted, released or its reservation
    runs out (``retry_after``)."""

    id: str
    queue: str
    payload: str
    attempts: int
    """How many times the job has been reserved, this time included."""
    receipt: str
    """The adapter's handle on this reservation, used to delete or release exactly this one."""


@dataclass(frozen=True)
class FailedJob:
    id: str
    queue: str
    payload: str
    exception: str
    failed_at: float


class AdapterABC(ABC):
    @abstractmethod
    def push(self, queue: str, id: str, payload: str, delay: float = 0) -> None: ...

    @abstractmethod
    def pop(self, queue: str) -> ReservedJob | None: ...

    @abstractmethod
    def delete(self, job: ReservedJob) -> None:
        """Remove a finished job. A no-op when the reservation ran out and another worker took the job."""

    @abstractmethod
    def release(self, job: ReservedJob, delay: float = 0) -> None:
        """Put a job back to be tried again after ``delay`` seconds."""

    @abstractmethod
    def fail(self, job: ReservedJob, exception: str) -> None:
        """Move a job to the failed jobs."""

    @abstractmethod
    def size(self, queue: str) -> int:
        """Jobs on ``queue``: waiting, delayed and reserved."""

    @abstractmethod
    def clear(self, queue: str) -> int: ...

    @abstractmethod
    def failed(self) -> list[FailedJob]:
        """Failed jobs, the most recent first."""

    @abstractmethod
    def find_failed(self, id: str) -> FailedJob | None: ...

    @abstractmethod
    def forget_failed(self, id: str) -> bool: ...

    @abstractmethod
    def flush_failed(self) -> int: ...

    def close(self) -> None:
        pass
