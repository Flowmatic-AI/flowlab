from __future__ import annotations

from dataclasses import dataclass

from flowlab.modules.db.query.ddl._alter import AlterABC
from flowlab.modules.db.query.ddl._unique_constraint import UniqueConstraint


@dataclass
class AddUniqueConstraint(UniqueConstraint, AlterABC):
    pass
