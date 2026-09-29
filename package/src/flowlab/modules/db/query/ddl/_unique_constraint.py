from __future__ import annotations

from dataclasses import dataclass

from flowlab.modules.db.query.ddl._constraint import ConstraintABC


@dataclass
class UniqueConstraint(ConstraintABC):
    columns: list[str]
    name: str | None = None
