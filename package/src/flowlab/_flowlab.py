from __future__ import annotations

import functools
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractContextManager, ExitStack, asynccontextmanager, contextmanager
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any, Self

import typer
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP
from fastmcp.utilities.lifespan import combine_lifespans
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from flowlab import _state
from flowlab._cache import connect_cache_store
from flowlab._commands import commands as builtin_commands
from flowlab._database import connect_database
from flowlab._exceptions import AuthNotEnabled, NotConnected
from flowlab._handlers import handle_exception, health
from flowlab._module import Module
from flowlab._queue import connect_queue
from flowlab._routing import Command, CommandRouter, Router
from flowlab._settings import (
    AuthSettings,
    CacheSettings,
    DatabaseSettings,
    FastAPISettings,
    FastMCPSettings,
    QueueSettings,
    TyperSettings,
)
from flowlab.modules import queue
from flowlab.modules.cache import Cache as CacheStore
from flowlab.modules.db import DB as Database
from flowlab.modules.migrator import Migrator
from flowlab.modules.migrator._schema import migrator as open_migrator
from flowlab.modules.migrator._schema import publish_migrations
from flowlab.modules.queue import Queue

if TYPE_CHECKING:
    from flowlab.modules.auth import BaseUser


def _caller_frame() -> FrameType:
    frame = sys._getframe(1)

    while frame.f_back is not None and frame.f_globals.get("__name__", "").startswith("flowlab."):
        frame = frame.f_back

    return frame


class FlowLab:
    def __init__(
        self,
        fastapi_settings: FastAPISettings | None = None,
        fastmcp_settings: FastMCPSettings | None = None,
        typer_settings: TyperSettings | None = None,
        *,
        database_settings: DatabaseSettings | None = None,
        cache_settings: CacheSettings | None = None,
        queue_settings: QueueSettings | None = None,
        auth_settings: AuthSettings | None = None,
        user_model: type[BaseUser] | None = None,
        project_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        _state.register(self)

        try:
            self._build(
                fastapi_settings or FastAPISettings(),
                fastmcp_settings or FastMCPSettings(),
                typer_settings or TyperSettings(),
                database_settings,
                cache_settings,
                queue_settings,
                auth_settings,
                user_model,
                project_dir,
                kwargs,
            )
        except BaseException:
            _state.unregister()
            raise

    @classmethod
    def instance(cls) -> Self:
        app = _state.get_app()

        if not isinstance(app, cls):
            raise TypeError(f"The initialized application is a {type(app).__name__}, not a {cls.__name__}")

        return app

    @classmethod
    def initialized(cls) -> bool:
        try:
            cls.instance()
        except RuntimeError:
            return False

        return True

    @classmethod
    def reset(cls) -> None:
        if cls.initialized():
            cls.instance()._close()

        _state.unregister()

    def _build(
        self,
        fastapi_settings: FastAPISettings,
        fastmcp_settings: FastMCPSettings,
        typer_settings: TyperSettings,
        database_settings: DatabaseSettings | None,
        cache_settings: CacheSettings | None,
        queue_settings: QueueSettings | None,
        auth_settings: AuthSettings | None,
        user_model: type[BaseUser] | None,
        project_dir: str | Path | None,
        kwargs: dict[str, Any],
    ) -> None:
        frame = _caller_frame()
        caller_file = frame.f_globals.get("__file__")

        self._module_name: str = frame.f_globals.get("__name__", "__main__")
        self._module_file = Path(caller_file).resolve() if caller_file else None

        if project_dir is not None:
            self.project_dir = Path(project_dir).resolve()
        elif self._module_file is not None:
            self.project_dir = self._module_file.parent
        else:
            self.project_dir = Path.cwd()

        self.fastapi_settings = fastapi_settings
        self.fastmcp_settings = fastmcp_settings
        self.typer_settings = typer_settings
        self.database_settings = database_settings or DatabaseSettings()
        self.cache_settings = cache_settings or CacheSettings()
        self.queue_settings = queue_settings or QueueSettings()
        self.auth_settings = auth_settings
        self._user_model = user_model

        self._db: Database | None = None
        self._cache: CacheStore | None = None
        self._queue: Queue | None = None

        self.modules: list[Module] = []
        self.migrations_dir = self.project_dir / "migrations"
        self._lifespans: list[Callable[[], AbstractContextManager[Any]]] = []
        self._mcp_app: Any = None

        self.mcp = FastMCP(fastmcp_settings.mcp_name)

        production = fastapi_settings.is_production

        self.api = FastAPI(
            **{
                "title": fastapi_settings.app_name,
                "docs_url": None if production else "/docs",
                "redoc_url": None if production else "/redoc",
                "openapi_url": None if production else "/openapi.json",
                **kwargs,
                "lifespan": self._asgi_lifespan,
            }
        )
        self.api.add_middleware(CORSMiddleware, **fastapi_settings.cors_options())
        self.api.add_exception_handler(Exception, handle_exception)
        self.api.add_api_route("/health", health, methods=["GET"], include_in_schema=False)

        self.cli = typer.Typer(
            name=typer_settings.cli_name,
            help=typer_settings.cli_help,
            no_args_is_help=True,
            add_completion=False,
            rich_markup_mode=None,
        )
        self.include_router(builtin_commands)
        self.include_module(queue.module())

        if auth_settings is not None:
            from flowlab.modules import auth

            if self._user_model is None:
                self._user_model = auth.User

            self.include_module(auth.module(self._user_model, registration=auth_settings.auth_registration))
        elif user_model is not None:
            raise AuthNotEnabled

    @property
    def db(self) -> Database:
        if self._db is None:
            raise NotConnected("database")

        return self._db

    @property
    def cache(self) -> CacheStore:
        if self._cache is None:
            raise NotConnected("cache")

        return self._cache

    @property
    def queue(self) -> Queue:
        if self._queue is None:
            raise NotConnected("queue")

        return self._queue

    @property
    def migrator(self) -> Migrator:
        return open_migrator(self.db, self.migrations_dir)

    @property
    def auth(self) -> AuthSettings:
        if self.auth_settings is None:
            raise AuthNotEnabled

        return self.auth_settings

    @property
    def user_model(self) -> type[BaseUser]:
        if self._user_model is None:
            raise AuthNotEnabled

        return self._user_model

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.asgi(scope, receive, send)

    @property
    def asgi(self) -> ASGIApp:
        self._mount_mcp()

        return self.api

    def run(self, args: list[str] | None = None) -> None:
        self.cli(args=args, prog_name=self._prog_name())

    def include_module(self, module: Module) -> None:
        if module in self.modules:
            return

        if module.setup is not None:
            module.setup(self)

        for router in module.routers:
            self.include_router(router)

        if module.migrations is not None:
            self.add_command(
                Command(f"{module.name}:install", _installer(module.name, module.migrations), lifespan=False)
            )

        if module.mcp_auth is not None:
            self.mcp.auth = module.mcp_auth()

        self.modules.append(module)

    def add_lifespan(self, factory: Callable[[], AbstractContextManager[Any]]) -> None:
        self._lifespans.append(factory)

    @contextmanager
    def lifespan(self) -> Iterator[None]:
        if self._db is not None:
            yield
            return

        with ExitStack() as stack:
            self._db = connect_database(self.database_settings, self.project_dir)
            stack.callback(self._close)

            self._cache = connect_cache_store(self.cache_settings, self._db)
            self._queue = connect_queue(self.queue_settings, self._db)

            for factory in self._lifespans:
                stack.enter_context(factory())

            yield

    def within_lifespan[**P, R](self, callback: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(callback)
        def run(*args: P.args, **kwargs: P.kwargs) -> R:
            with self.lifespan():
                return callback(*args, **kwargs)

        return run

    def add_command(self, command: Command) -> None:
        callback = self.within_lifespan(command.callback) if command.lifespan else command.callback
        panel = command.panel or command.name.partition(":")[0]

        self.cli.command(command.name, rich_help_panel=panel, **command.options)(callback)

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

    def include_router(self, router: Router, **kwargs: Any) -> None:
        if isinstance(router, APIRouter):
            self.api.include_router(router, **kwargs)
        elif isinstance(router, FastMCP):
            self.mcp.mount(router, **kwargs)
        elif isinstance(router, CommandRouter):
            if kwargs:
                raise TypeError(f"A CommandRouter takes no include options, got {', '.join(sorted(kwargs))}")

            for command in router.commands:
                self.add_command(command)
        else:
            raise TypeError(
                f"Cannot include {type(router).__name__}; expected an APIRouter, MCPRouter or CommandRouter"
            )

    def add_middleware(self, *args: Any, **kwargs: Any) -> None:
        self.api.add_middleware(*args, **kwargs)

    def exception_handler(self, *args: Any, **kwargs: Any) -> Any:
        return self.api.exception_handler(*args, **kwargs)

    def middleware(self, *args: Any, **kwargs: Any) -> Any:
        return self.api.middleware(*args, **kwargs)

    def api_route(self, *args: Any, **kwargs: Any) -> Any:
        return self.api.api_route(*args, **kwargs)

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self.api.get(*args, **kwargs)

    def post(self, *args: Any, **kwargs: Any) -> Any:
        return self.api.post(*args, **kwargs)

    def put(self, *args: Any, **kwargs: Any) -> Any:
        return self.api.put(*args, **kwargs)

    def patch(self, *args: Any, **kwargs: Any) -> Any:
        return self.api.patch(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        return self.api.delete(*args, **kwargs)

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        return self.mcp.tool(*args, **kwargs)

    def resource(self, *args: Any, **kwargs: Any) -> Any:
        return self.mcp.resource(*args, **kwargs)

    def prompt(self, *args: Any, **kwargs: Any) -> Any:
        return self.mcp.prompt(*args, **kwargs)

    def _close(self) -> None:
        queue, self._queue = self._queue, None
        cache, self._cache = self._cache, None
        db, self._db = self._db, None

        if queue is not None:
            queue.close()

        if cache is not None:
            cache.close()

        if db is not None:
            db.close()

    def _mount_mcp(self) -> Any:
        if self._mcp_app is None:
            path = self.fastmcp_settings.mcp_path

            self._mcp_app = self.mcp.http_app(
                path=path,
                stateless_http=self.fastmcp_settings.mcp_stateless_http,
                json_response=self.fastmcp_settings.mcp_json_response,
            )
            self.api.router.routes.append(Route(path, self._mcp_app, methods=["GET", "POST", "DELETE"]))

        return self._mcp_app

    @asynccontextmanager
    async def _asgi_lifespan(self, app: Any) -> AsyncIterator[None]:
        mcp_app = self._mount_mcp()

        async with combine_lifespans(self._core_asgi_lifespan, mcp_app.lifespan)(app):
            yield

    @asynccontextmanager
    async def _core_asgi_lifespan(self, app: Any) -> AsyncIterator[None]:
        with self.lifespan():
            self.check_modules()
            yield

    def check_modules(self) -> None:
        for module in self.modules:
            if module.check is not None:
                module.check(self.db)

    def _prog_name(self) -> str:
        if self.typer_settings.cli_name:
            return self.typer_settings.cli_name

        if self._module_name == "__main__" and self._module_file is not None:
            return f"python {self._module_file.name}"

        return "flowlab"

    def _import_string(self) -> str:
        module = sys.modules.get(self._module_name)

        if module is None or self._module_file is None:
            raise RuntimeError("Reload needs the app to be created at module level in a Python file")

        attribute = next((name for name, value in vars(module).items() if value is self), None)

        if attribute is None:
            raise RuntimeError("Reload needs the app to be assigned to a module-level variable")

        module_name = self._module_file.stem if self._module_name == "__main__" else self._module_name

        return f"{module_name}:{attribute}"


def _installer(name: str, templates: Path) -> Callable[[], None]:
    def install() -> None:
        published = publish_migrations(templates, _state.get_app().migrations_dir)

        for path in published:
            typer.echo(f"Published {path.name}")

        if not published:
            typer.echo(f"The {name} migrations are already in this project.")

    install.__doc__ = f"Copy the {name} migrations this project does not have yet into migrations/."

    return install
