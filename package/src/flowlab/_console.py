import importlib
import os
import sys

from flowlab._commands import RELOAD_TARGET_ENV
from flowlab._flowlab import FlowLab

DEFAULT_APP = "main:app"


def load_app(target: str) -> FlowLab:
    module_name, _, attribute = target.partition(":")
    sys.path.insert(0, os.getcwd())

    app = getattr(importlib.import_module(module_name), attribute or "app")

    if not isinstance(app, FlowLab):
        raise SystemExit(f"{target} is not a FlowLab application")

    return app


def reload_target() -> FlowLab:
    if FlowLab.initialized():
        return FlowLab.instance()

    return load_app(os.environ[RELOAD_TARGET_ENV])


def main() -> None:
    args = sys.argv[1:]
    target = os.environ.get("FLOWLAB_APP", DEFAULT_APP)

    if len(args) >= 2 and args[0] == "--app":
        target, args = args[1], args[2:]

    load_app(target).run(args)
