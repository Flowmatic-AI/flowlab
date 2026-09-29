from __future__ import annotations

import functools
import json
import threading
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool

from flowlab._settings import QueueDriver
from flowlab._state import get_app
from flowlab.modules.queue._worker import Worker
from flowlab.modules.queue.adapters._base import ReservedJob
from flowlab.modules.queue.adapters._cloud_tasks import ATTEMPTS_HEADER

if TYPE_CHECKING:
    from flowlab._flowlab import FlowLab

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
MIN_REFRESH_INTERVAL = 60

Verifier = Callable[[str], bool]


class GoogleTokenVerifier:
    """Accepts a Google-signed OIDC token for ``audience`` issued to ``service_account``. Google's signing certificates
    are fetched once and kept for ``ttl`` seconds, or until a token names a key they don't have (at most once a
    minute, so forged tokens can't make every request fetch them)."""

    def __init__(self, audience: str, service_account: str, ttl: float = 3600) -> None:
        self.audience = audience
        self.service_account = service_account
        self.ttl = ttl
        self._certs: dict[str, str] = {}
        self._fetched_at: float | None = None
        self._lock = threading.Lock()

    def __call__(self, token: str) -> bool:
        from google.auth import jwt

        try:
            kid = jwt.decode_header(token).get("kid")  # type: ignore[no-untyped-call]
            certs = self._certificates(refresh=kid not in self._certs)
            claims = jwt.decode(token, certs=certs, audience=self.audience)  # type: ignore[no-untyped-call]
        except (ValueError, KeyError, TypeError):
            return False

        return (
            claims.get("iss") in GOOGLE_ISSUERS
            and claims.get("email") == self.service_account
            and claims.get("email_verified") is True
        )

    def _certificates(self, refresh: bool) -> dict[str, str]:
        with self._lock:
            age = float("inf") if self._fetched_at is None else time.monotonic() - self._fetched_at

            if age > self.ttl or (refresh and age > MIN_REFRESH_INTERVAL):
                from google.auth.transport.requests import Request as TransportRequest

                response = TransportRequest()(GOOGLE_CERTS_URL, method="GET")

                if response.status != 200:
                    raise ValueError(f"Could not fetch Google's certificates: HTTP {response.status}")

                self._certs = json.loads(response.data)
                self._fetched_at = time.monotonic()

            return self._certs


def setup(app: FlowLab) -> None:
    """Add the route Cloud Tasks pushes jobs to, when the queue driver is ``cloudtasks``."""
    settings = app.queue_settings

    if settings.queue_driver is not QueueDriver.CLOUDTASKS:
        return

    assert settings.queue_target_url is not None and settings.queue_service_account is not None
    verifier = GoogleTokenVerifier(settings.queue_target_url, settings.queue_service_account)

    async def endpoint(request: Request) -> Response:
        return await run_pushed_job(request, verifier)

    app.api.add_api_route(settings.queue_push_path, endpoint, methods=["POST"], include_in_schema=False)


async def run_pushed_job(request: Request, verify: Verifier) -> Response:
    """Run the job in the request body, the way a worker runs one it popped.

    Any 2xx tells Cloud Tasks the task is done, so a job that raised also gets one once it has been scheduled again
    or moved to the failed jobs. A 5xx (the app itself failing) and no answer within the deadline make Cloud Tasks
    retry the same task, following the queue's retry config.
    """
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")

    if scheme.lower() != "bearer" or not await run_in_threadpool(verify, token):
        return Response(status_code=401)

    queue = get_app().queue
    job = pushed_job((await request.body()).decode(), request.headers, queue.default)
    worker = Worker(queue, log=functools.partial(print, flush=True))
    await run_in_threadpool(worker.process, job)

    return Response(status_code=204)


def pushed_job(payload: str, headers: Mapping[str, str], default_queue: str) -> ReservedJob:
    task = headers.get("X-CloudTasks-TaskName", "")
    earlier = _int(headers.get(ATTEMPTS_HEADER)) + _int(headers.get("X-CloudTasks-TaskRetryCount"))

    return ReservedJob(
        id=_job_id(payload) or task,
        queue=headers.get("X-CloudTasks-QueueName", default_queue),
        payload=payload,
        attempts=earlier + 1,
        receipt=task,
    )


def _job_id(payload: str) -> str | None:
    try:
        return str(json.loads(payload)["id"])
    except (ValueError, KeyError, TypeError):
        return None


def _int(value: str | None) -> int:
    try:
        return max(int(value or 0), 0)
    except ValueError:
        return 0
