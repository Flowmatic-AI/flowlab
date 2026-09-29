from __future__ import annotations

from dataclasses import dataclass

from flowlab.modules.db.query.ddl._alter import AlterABC
from flowlab.modules.db.query.ddl._foreign_key_constraint import ForeignKeyConstraint


@dataclass
class AddForeignKeyConstraint(ForeignKeyConstraint, AlterABC):
    pass
