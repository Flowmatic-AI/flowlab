from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OnConflict:
    conflict: str | list[str]
    updates: dict[str, Any] | None = None
