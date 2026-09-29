from __future__ import annotations

from dataclasses import dataclass

from flowlab.modules.db.query.ddl._constraint import ConstraintABC
from flowlab.modules.db.query.enums import ReferentialActionEnum


@dataclass
class ForeignKeyConstraint(ConstraintABC):
    columns: list[str]
    ref_table: str
    ref_columns: list[str]
    name: str | None = None
    on_delete: ReferentialActionEnum | str | None = None
    on_update: ReferentialActionEnum | str | None = None
