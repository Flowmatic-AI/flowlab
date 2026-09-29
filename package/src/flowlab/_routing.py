from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter
from fastmcp import FastMCP


@dataclass(frozen=True)
class Command:
    name: str
    callback: Callable[..., Any]
    panel: str | None = None
    lifespan: bool = True
    options: dict[str, Any] = field(default_factory=dict)


class CommandRouter:
    def __init__(self) -> None:
        self.commands: list[Command] = []

    def add_command(self, command: Command) -> None:
        self.commands.append(command)

    def command[F: Callable[..., Any]](
        self,
        name: str,
        *,
        panel: str | None = None,
        lifespan: bool = True,
        **options: Any,
    ) -> Callable[[F], F]:
        def register(callback: F) -> F:
            self.add_command(Command(name, callback, panel=panel, lifespan=lifespan, options=options))

            return callback

        return register


class MCPRouter(FastMCP[Any]):
    def __init__(self, name: str = "router", **kwargs: Any) -> None:
        super().__init__(name, **kwargs)


Router = APIRouter | FastMCP[Any] | CommandRouter
