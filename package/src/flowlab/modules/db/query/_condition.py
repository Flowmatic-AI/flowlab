from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flowlab.modules.db.query.enums import ChainEnum, ConditionEnum

if TYPE_CHECKING:
    from flowlab.modules.db.query.expressions import SqlABC


@dataclass
class Condition:
    condition: ConditionEnum | str
    identifier: str | list[str] | SqlABC | None = None
    value: Any = None
    chain: ChainEnum = ChainEnum.AND
    cast: bool = False
    case_insensitive: bool = False
    flags: str | None = None
