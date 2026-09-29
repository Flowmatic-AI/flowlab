from __future__ import annotations

import re

MIGRATION_TEMPLATE: str = """from __future__ import annotations

from typing import TYPE_CHECKING

from flowlab.modules.migrator import MigrationABC

if TYPE_CHECKING:
    from flowlab.modules.db import DB


class {class_name}(MigrationABC):
    def up(self, db: DB) -> None:
        pass

    def down(self, db: DB) -> None:
        pass
"""


def migration_class_name(name: str) -> str:
    parts = [part for part in re.split(r"[^0-9a-zA-Z]+", name) if part]
    class_name = "".join(part[0].upper() + part[1:] for part in parts)

    if not class_name or class_name[0].isdigit():
        class_name = f"Migration{class_name}"

    return class_name


def render_migration(name: str) -> str:
    return MIGRATION_TEMPLATE.format(class_name=migration_class_name(name))
