from __future__ import annotations

from typing import TYPE_CHECKING

from flowlab._exceptions import FlowLabAlreadyInitialized, FlowLabNotInitialized

if TYPE_CHECKING:
    from flowlab._flowlab import FlowLab

_app: FlowLab | None = None


def register(app: FlowLab) -> None:
    global _app

    if _app is not None:
        raise FlowLabAlreadyInitialized

    _app = app


def unregister() -> None:
    global _app

    _app = None


def get_app() -> FlowLab:
    if _app is None:
        raise FlowLabNotInitialized

    return _app
