from __future__ import annotations

from dataclasses import dataclass

from flowlab.modules.db.query.ddl._alter import AlterABC
from flowlab.modules.db.query.ddl._column import Column


@dataclass
class AddColumn(Column, AlterABC):
    pass
