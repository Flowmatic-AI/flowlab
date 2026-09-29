from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fastmcp.server.auth import AuthProvider

from flowlab._routing import Router
from flowlab.modules.db.database import DB as Database

if TYPE_CHECKING:
    from flowlab._flowlab import FlowLab


@dataclass(frozen=True)
class Module:
    name: str
    routers: Sequence[Router] = ()
    migrations: Path | None = None
    mcp_auth: Callable[[], AuthProvider] | None = None
    setup: Callable[[FlowLab], None] | None = None
    check: Callable[[Database], None] | None = None
