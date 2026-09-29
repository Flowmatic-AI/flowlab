from __future__ import annotations

from typing import TYPE_CHECKING

from flowlab.modules.migrator import MigrationABC

if TYPE_CHECKING:
    from flowlab.modules.db import DB


class CreateJobsTable(MigrationABC):
    def up(self, db: DB) -> None:
        (
            db.create_table("jobs")
            .auto_increment("id")
            .string("uuid", not_null=True)
            .string("queue", not_null=True)
            .text("payload", not_null=True)
            .integer("attempts", not_null=True)
            .string("reservation")
            .float("available_at", not_null=True)
            .float("created_at", not_null=True)
            .execute()
        )
        db.create_index("jobs", "jobs_queue_available_at_index").columns(["queue", "available_at"]).execute()

        (
            db.create_table("failed_jobs")
            .auto_increment("id")
            .string("uuid", not_null=True)
            .string("queue", not_null=True)
            .text("payload", not_null=True)
            .text("exception", not_null=True)
            .float("failed_at", not_null=True)
            .unique_constraint(["uuid"])
            .execute()
        )

    def down(self, db: DB) -> None:
        db.drop_table("failed_jobs").execute()
        db.drop_table("jobs").execute()
