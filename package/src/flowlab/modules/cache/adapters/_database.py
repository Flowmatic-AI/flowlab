from __future__ import annotations

import base64
import pickle
import secrets
import time
from typing import TYPE_CHECKING, Any

from flowlab.modules.cache.adapters._base import AdapterABC

if TYPE_CHECKING:
    from flowlab.modules.db.database import DB


class DatabaseAdapter(AdapterABC):
    def __init__(self, db: DB, table: str = "cache") -> None:
        self._db = db
        self._table = table
        self._ensure_table()

    def _ensure_table(self) -> None:
        (
            self._db.create_table(self._table)
            .if_not_exists()
            .string("key", not_null=True)
            .text("value", not_null=True)
            .float("expires_at")
            .primary_keys("key")
            .execute()
        )

    def get(self, key: str) -> Any:
        row = self._db.select(self._table).where_equals("key", key).execute().fetch_dict()

        if row is None:
            return None

        if row["expires_at"] is not None and row["expires_at"] < time.time():
            self.delete(key)
            return None

        return pickle.loads(base64.b64decode(row["value"]))

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        expires_at = time.time() + ttl if ttl is not None else None
        encoded = base64.b64encode(pickle.dumps(value)).decode("ascii")

        (
            self._db.insert(self._table)
            .values({"key": key, "value": encoded, "expires_at": expires_at})
            .on_conflict_do_update(["key"], {"value": encoded, "expires_at": expires_at})
            .execute()
        )

    def increment(self, key: str, amount: int = 1, ttl: float | None = None) -> int:
        # Compare-and-set without row locks: each write tags the value with a fresh nonce and only replaces the
        # value it read. Reading the tag back tells whether this write won; a lost race retries.
        while True:
            now = time.time()
            row = self._db.select(self._table).where_equals("key", key).execute().fetch_dict()
            tag = secrets.token_hex(8)

            if row is None or (row["expires_at"] is not None and row["expires_at"] < now):
                value, expires_at = amount, now + ttl if ttl is not None else None
            else:
                value, expires_at = int(row["value"].partition(":")[0]) + amount, row["expires_at"]

            stored = f"{value}:{tag}"

            if row is None:
                (
                    self._db.insert(self._table)
                    .values({"key": key, "value": stored, "expires_at": expires_at})
                    .on_conflict_do_nothing(["key"])
                    .execute()
                )
            else:
                (
                    self._db.update(self._table)
                    .set({"value": stored, "expires_at": expires_at})
                    .where_equals("key", key)
                    .where_equals("value", row["value"])
                    .execute()
                )

            current = self._db.select(self._table).columns(["value"]).where_equals("key", key).execute().fetch_dict()

            if current is not None and current["value"] == stored:
                return value

    def delete(self, key: str) -> None:
        self._db.delete(self._table).where_equals("key", key).execute()

    def exists(self, key: str) -> bool:
        row = self._db.select(self._table).columns(["expires_at"]).where_equals("key", key).execute().fetch_dict()

        if row is None:
            return False

        if row["expires_at"] is not None and row["expires_at"] < time.time():
            self.delete(key)
            return False

        return True

    def clear(self) -> None:
        self._db.delete(self._table).execute()
