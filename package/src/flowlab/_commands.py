import os
import subprocess
import sys
from typing import Annotated

import typer
import uvicorn

from flowlab._routing import CommandRouter
from flowlab._state import get_app
from flowlab.modules.migrator import drop_all_tables
from flowlab.modules.migrator._schema import scaffold

RELOAD_TARGET_ENV = "FLOWLAB_RELOAD_TARGET"

commands = CommandRouter()


@commands.command("server:start", lifespan=False, help="Serve the HTTP API and the MCP server with uvicorn.")
def server_start(
    host: Annotated[str | None, typer.Option(help="Interface to bind. Defaults to SERVER_HOST.")] = None,
    port: Annotated[int | None, typer.Option(help="Port to bind. Defaults to SERVER_PORT.")] = None,
    reload: Annotated[
        bool | None, typer.Option(help="Restart on code changes. Defaults to on when APP_ENV=local.")
    ] = None,
) -> None:
    app = get_app()
    settings = app.fastapi_settings
    host = settings.server_host if host is None else host
    port = settings.server_port if port is None else port
    reload = settings.is_local if reload is None else reload

    if not reload:
        uvicorn.run(app, host=host, port=port)
        return

    os.environ[RELOAD_TARGET_ENV] = app._import_string()

    uvicorn.run(
        "flowlab._console:reload_target",
        factory=True,
        host=host,
        port=port,
        reload=True,
        app_dir=str(app.project_dir),
        reload_dirs=[str(app.project_dir)],
    )


@commands.command("migrations:init", help="Create the table that records applied migrations.")
def migrations_init() -> None:
    _ = get_app().migrator
    typer.echo("Migrations table is ready.")


@commands.command("migrations:up", help="Apply every pending migration.")
def migrations_up() -> None:
    get_app().migrator.up()
    typer.echo("Migrated.")


@commands.command("migrations:down", help="Roll back the most recent batch of migrations.")
def migrations_down() -> None:
    get_app().migrator.down()
    typer.echo("Rolled back the last batch.")


@commands.command("migrations:fresh", help="Drop every table, then apply every migration.")
def migrations_fresh(
    force: Annotated[bool, typer.Option("--force", help="Required when APP_ENV is production.")] = False,
) -> None:
    app = get_app()

    if app.fastapi_settings.is_production and not force:
        typer.echo("Refusing to drop every table in production without --force.", err=True)
        raise typer.Exit(1)

    for table in drop_all_tables(app.db):
        typer.echo(f"Dropped {table}")

    app.migrator.up()
    typer.echo("Migrated.")


@commands.command("migrations:make", help="Create a new, empty migration file in migrations/.")
def migrations_make(
    name: Annotated[str, typer.Argument(help="snake_case description, e.g. create_posts_table")],
) -> None:
    app = get_app()
    typer.echo(scaffold(app.db, app.migrations_dir, name))


@commands.command(
    "test",
    lifespan=False,
    help="Run the project's tests with pytest; extra arguments go to pytest.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run_tests(ctx: typer.Context) -> None:
    result = subprocess.run([sys.executable, "-m", "pytest", *ctx.args], cwd=get_app().project_dir, check=False)

    raise typer.Exit(result.returncode)
