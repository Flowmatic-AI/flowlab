from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Excluded:
    identifier: str | None = None


@dataclass
class Values(Excluded):
    pass
