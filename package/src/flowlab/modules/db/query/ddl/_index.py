from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Index:
    name: str
    columns: list[str]
    unique: bool = False
