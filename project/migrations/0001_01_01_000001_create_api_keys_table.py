from __future__ import annotations

from typing import TYPE_CHECKING

from flowlab.modules.db.query.enums import ReferentialActionEnum
from flowlab.modules.migrator import MigrationABC

if TYPE_CHECKING:
    from flowlab.modules.db.database import DB


class CreateApiKeysTable(MigrationABC):
    def up(self, db: DB) -> None:
        db.create_table("api_keys")\
            .auto_increment("id")\
            .integer("user_id", not_null=True)\
            .text("name", not_null=True)\
            .text("hint", not_null=True)\
            .string("token_hash", not_null=True)\
            .current_timestamp("created_at", not_null=True)\
            .current_timestamp("updated_at", not_null=True)\
            .datetime("deleted_at")\
            .unique_constraint(["token_hash"])\
            .foreign_key_constraint("user_id", "users", "id", on_delete=ReferentialActionEnum.CASCADE)\
            .execute()

        db.create_index("api_keys", "api_keys_user_id_index")\
            .columns(["user_id"])\
            .execute()

    def down(self, db: DB) -> None:
        db.drop_table("api_keys").execute()
