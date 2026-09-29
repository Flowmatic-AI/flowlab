from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from flowlab.modules.db.query.enums import UnionEnum

if TYPE_CHECKING:
    from flowlab.modules.db.query._select import SelectQuery


@dataclass
class Union:
    union: UnionEnum
    select_query: SelectQuery
