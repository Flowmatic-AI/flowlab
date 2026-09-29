from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flowlab.modules.db.database import DB


class MigrationABC(ABC):
    @abstractmethod
    def up(self, db: DB) -> None:
        pass

    @abstractmethod
    def down(self, db: DB) -> None:
        pass

    def in_transaction(self) -> bool:
        return True
