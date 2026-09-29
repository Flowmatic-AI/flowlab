from __future__ import annotations

import secrets
import time
from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query.expressions import Raw
from flowlab.modules.queue.adapters._base import AdapterABC, FailedJob, ReservedJob

if TYPE_CHECKING:
    from flowlab.modules.db.database import DB


class DatabaseAdapter(AdapterABC):
    """Jobs in the ``jobs`` and ``failed_jobs`` tables of the queue migration.

    Reserving a job moves its ``available_at`` to when the reservation runs out, so one condition,
    ``available_at <= now``, finds both waiting jobs and jobs whose worker died. The reservation itself is a
    compare-and-set on the ``reservation`` column: no row locks, so it works the same on every database.
    """

    def __init__(self, db: DB, retry_after: float = 90, table: str = "jobs", failed_table: str = "failed_jobs") -> None:
        self._db = db
        self._retry_after = retry_after
        self._table = table
        self._failed_table = failed_table

    def push(self, queue: str, id: str, payload: str, delay: float = 0) -> None:
        now = time.time()

        (
            self._db.insert(self._table)
            .values(
                {
                    "uuid": id,
                    "queue": queue,
                    "payload": payload,
                    "attempts": 0,
                    "available_at": now + delay,
                    "created_at": now,
                }
            )
            .execute()
        )

    def pop(self, queue: str) -> ReservedJob | None:
        while True:
            now = time.time()
            row = (
                self._db.select(self._table)
                .where_equals("queue", queue)
                .where_less_than_or_equals("available_at", now)
                .order_by_asc("id")
                .limit(1)
                .execute()
                .fetch_dict()
            )

            if row is None:
                return None

            token = secrets.token_hex(8)
            claim = (
                self._db.update(self._table)
                .set({"reservation": token, "attempts": row["attempts"] + 1, "available_at": now + self._retry_after})
                .where_equals("id", row["id"])
            )

            if row["reservation"] is None:
                claim.where_is_null("reservation")
            else:
                claim.where_equals("reservation", row["reservation"])

            claim.execute()

            if self._reservation(row["id"]) == token:
                return ReservedJob(
                    id=row["uuid"],
                    queue=queue,
                    payload=row["payload"],
                    attempts=row["attempts"] + 1,
                    receipt=f"{row['id']}:{token}",
                )

    def delete(self, job: ReservedJob) -> None:
        row_id, token = self._parse(job)
        self._db.delete(self._table).where_equals("id", row_id).where_equals("reservation", token).execute()

    def release(self, job: ReservedJob, delay: float = 0) -> None:
        row_id, token = self._parse(job)

        (
            self._db.update(self._table)
            .set({"reservation": None, "available_at": time.time() + delay})
            .where_equals("id", row_id)
            .where_equals("reservation", token)
            .execute()
        )

    def fail(self, job: ReservedJob, exception: str) -> None:
        def move(db: DB) -> None:
            db.insert(self._failed_table).values(
                {
                    "uuid": job.id,
                    "queue": job.queue,
                    "payload": job.payload,
                    "exception": exception,
                    "failed_at": time.time(),
                }
            ).execute()
            self.delete(job)

        self._db.transaction(move)

    def size(self, queue: str) -> int:
        return self._count(self._db.select(self._table).where_equals("queue", queue))

    def clear(self, queue: str) -> int:
        count = self.size(queue)
        self._db.delete(self._table).where_equals("queue", queue).execute()
        return count

    def failed(self) -> list[FailedJob]:
        rows = self._db.select(self._failed_table).order_by_desc("id").execute().fetch_dicts()
        return [self._failed_job(row) for row in rows]

    def find_failed(self, id: str) -> FailedJob | None:
        row = self._db.select(self._failed_table).where_equals("uuid", id).execute().fetch_dict()
        return None if row is None else self._failed_job(row)

    def forget_failed(self, id: str) -> bool:
        if self.find_failed(id) is None:
            return False

        self._db.delete(self._failed_table).where_equals("uuid", id).execute()
        return True

    def flush_failed(self) -> int:
        count = self._count(self._db.select(self._failed_table))
        self._db.delete(self._failed_table).execute()
        return count

    def _reservation(self, row_id: int) -> str | None:
        row = self._db.select(self._table).columns(["reservation"]).where_equals("id", row_id).execute().fetch_dict()
        return None if row is None else row["reservation"]

    @staticmethod
    def _count(query: Any) -> int:
        return int(query.columns([Raw("COUNT(*) AS total")]).execute().scalar("total") or 0)

    @staticmethod
    def _parse(job: ReservedJob) -> tuple[int, str]:
        row_id, _, token = job.receipt.partition(":")
        return int(row_id), token

    @staticmethod
    def _failed_job(row: dict[str, Any]) -> FailedJob:
        return FailedJob(
            id=row["uuid"],
            queue=row["queue"],
            payload=row["payload"],
            exception=row["exception"],
            failed_at=row["failed_at"],
        )
