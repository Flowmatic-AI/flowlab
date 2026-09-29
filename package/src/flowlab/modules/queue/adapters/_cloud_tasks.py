from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from flowlab.modules.queue.adapters._base import AdapterABC, FailedJob, ReservedJob
from flowlab.modules.queue.adapters._database import DatabaseAdapter

ATTEMPTS_HEADER = "X-Flowlab-Attempts"

# Cloud Tasks accepts a dispatch deadline between 15 seconds and 30 minutes.
MIN_DEADLINE = 15
MAX_DEADLINE = 1800


class CloudTasksAdapter(AdapterABC):
    """Jobs as Google Cloud Tasks that call the app back over HTTP, so nothing polls and the service can scale to zero.

    Each flowlab queue is the Cloud Tasks queue of the same name. A task POSTs the payload to ``url`` with an OIDC
    token for ``service_account``; the app's push route runs it. Workers never pop: ``pop`` is always ``None``.
    A retry after ``backoff`` is a new task that carries the attempts so far in ``X-Flowlab-Attempts``, and failed
    jobs go to the ``failed_jobs`` table through ``failed_jobs``, since Cloud Tasks drops what it gives up on.
    """

    def __init__(
        self,
        failed_jobs: DatabaseAdapter,
        *,
        project: str,
        location: str,
        url: str,
        service_account: str,
        audience: str | None = None,
        retry_after: float = 90,
        client: Any = None,
    ) -> None:
        if client is None:
            from google.cloud import tasks_v2

            client = tasks_v2.CloudTasksClient()

        self._client = client
        self._failed = failed_jobs
        self._project = project
        self._location = location
        self._url = url
        self._service_account = service_account
        self._audience = audience or url
        self._deadline = timedelta(seconds=min(max(retry_after, MIN_DEADLINE), MAX_DEADLINE))

    def push(self, queue: str, id: str, payload: str, delay: float = 0) -> None:
        self._create(queue, payload, delay, attempts=0)

    def pop(self, queue: str) -> ReservedJob | None:
        return None

    def delete(self, job: ReservedJob) -> None:
        """Nothing to do: answering the push request with a 2xx is what finishes the task."""

    def release(self, job: ReservedJob, delay: float = 0) -> None:
        self._create(job.queue, job.payload, delay, attempts=job.attempts)

    def fail(self, job: ReservedJob, exception: str) -> None:
        self._failed.record_failure(job, exception)

    def size(self, queue: str) -> int:
        """Tasks on ``queue``, counted by listing them all, so slow on a long queue."""
        return sum(1 for _ in self._client.list_tasks(parent=self._path(queue)))

    def clear(self, queue: str) -> int:
        count = self.size(queue)
        self._client.purge_queue(name=self._path(queue))
        return count

    def failed(self) -> list[FailedJob]:
        return self._failed.failed()

    def find_failed(self, id: str) -> FailedJob | None:
        return self._failed.find_failed(id)

    def forget_failed(self, id: str) -> bool:
        return self._failed.forget_failed(id)

    def flush_failed(self) -> int:
        return self._failed.flush_failed()

    def close(self) -> None:
        self._client.transport.close()

    def _create(self, queue: str, payload: str, delay: float, attempts: int) -> None:
        task: dict[str, Any] = {
            "http_request": {
                "http_method": "POST",
                "url": self._url,
                "headers": {"Content-Type": "application/json", ATTEMPTS_HEADER: str(attempts)},
                "body": payload.encode(),
                "oidc_token": {"service_account_email": self._service_account, "audience": self._audience},
            },
            "dispatch_deadline": self._deadline,
        }

        if delay > 0:
            task["schedule_time"] = datetime.now(UTC) + timedelta(seconds=delay)

        self._client.create_task(parent=self._path(queue), task=task)

    def _path(self, queue: str) -> str:
        return f"projects/{self._project}/locations/{self._location}/queues/{queue}"
