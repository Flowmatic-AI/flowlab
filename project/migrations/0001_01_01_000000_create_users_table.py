from __future__ import annotations

from typing import TYPE_CHECKING

from flowlab.modules.migrator import MigrationABC

if TYPE_CHECKING:
    from flowlab.modules.db.database import DB


class CreateUsersTable(MigrationABC):
    def up(self, db: DB) -> None:
        db.create_table("users")\
            .auto_increment("id")\
            .string("email", not_null=True)\
            .string("password", not_null=True)\
            .current_timestamp("created_at", not_null=True)\
            .current_timestamp("updated_at", not_null=True)\
            .datetime("deleted_at")\
            .unique_constraint(["email"])\
            .execute()

    def down(self, db: DB) -> None:
        db.drop_table("users").execute()
