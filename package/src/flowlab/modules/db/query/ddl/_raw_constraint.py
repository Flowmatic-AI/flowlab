from __future__ import annotations

from dataclasses import dataclass

from flowlab.modules.db.query.ddl._constraint import ConstraintABC


@dataclass
class RawConstraint(ConstraintABC):
    sql: str
