from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flowlab.modules.db.query.enums import OrderByDirectionEnum

if TYPE_CHECKING:
    from flowlab.modules.db.query.expressions import SqlABC


@dataclass
class OrderBy:
    column: str | list[str] | SqlABC
    direction: OrderByDirectionEnum = OrderByDirectionEnum.ASC
