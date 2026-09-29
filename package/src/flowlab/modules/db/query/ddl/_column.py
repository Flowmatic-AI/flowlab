from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flowlab.modules.db.query.enums import TypeEnum


@dataclass
class Column:
    name: str
    type: TypeEnum | str
    size: int | None = None
    not_null: bool = False
    default: Any = None
    auto_increment: bool = False
