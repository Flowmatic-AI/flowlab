from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flowlab.modules.db.dialects import DialectABC


class SqlABC(ABC):
    @abstractmethod
    def sql(self, dialect: DialectABC) -> str: ...

    @abstractmethod
    def params(self, dialect: DialectABC) -> list[Any]: ...

    @abstractmethod
    def raw_sql(self, dialect: DialectABC) -> str: ...
