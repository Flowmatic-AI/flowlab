# flowlab

An API framework like FastAPI that also serves an MCP server at `/mcp` and runs
console commands, all from one app object. Database, cache, migrations and auth
are built in.

```bash
pip install flowlab
```

```python
from flowlab import AuthSettings, FlowLab

app = FlowLab(auth_settings=AuthSettings())


@app.get("/")
def index() -> dict[str, str]:
    return {"message": "Hello"}


@app.tool
def hello(name: str) -> str:
    return f"Hello, {name}!"


@app.command("hello:say")
def say(name: str) -> None:
    print(f"Hello, {name}!")


if __name__ == "__main__":
    app.run()
```

Every migration lives in the project's `migrations/` folder, including the
ones auth needs. `python main.py auth:install` copies them in (the starter
project already has them). For extra user fields, pass your own `user_model`;
see [docs/auth.md](https://github.com/Flowmatic-AI/flowlab/blob/main/package/docs/auth.md#your-user-model).

```bash
python main.py auth:install      # once: copies the users and api_keys migrations into migrations/
python main.py migrations:up
python main.py server:start      # or: flowlab server:start (loads main:app from the cwd)
```

## The FlowLab class

`FlowLab(fastapi_settings=None, fastmcp_settings=None, typer_settings=None, *, database_settings=None, cache_settings=None, auth_settings=None, user_model=None, project_dir=None, **kwargs)`

Every settings argument is optional; when it's left out, the settings are read
from the environment and `.env`.

FlowLab is a singleton: the database, cache, migrator and auth live on the one
app.

- `FlowLab.instance()` returns the app. Before one is created it raises
  `FlowLabNotInitialized`, and so do `get_db()`, `get_cache()` and the `DB` /
  `Cache` dependencies. Creating a second app raises
  `FlowLabAlreadyInitialized`. `FlowLab.reset()` closes and forgets the app
  (for tests); `FlowLab.initialized()` says whether one exists.
- `app.db`, `app.cache`: the open connections. Outside `app.lifespan()` (or a
  running server / command) they raise `NotConnected`.
- `app.migrator`: a `Migrator` over the project's `migrations/` folder
  (`app.migrations_dir`). The package never runs migrations of its own.
- `app.auth`: the `AuthSettings`. Auth is on when `auth_settings` is passed,
  which wires its routes, MCP tools and commands; otherwise
  `app.auth` raises `AuthNotEnabled`.
- `**kwargs` are passed to `FastAPI(...)`.
- `project_dir` defaults to the directory of the file that creates the app. A
  relative sqlite `DB_NAME` and the `migrations/` folder resolve against it.
- `app` is itself an ASGI app (`uvicorn main:app` works). `app.api` is the
  FastAPI instance, `app.mcp` the FastMCP server, `app.cli` the Typer app.
- Routes: `app.get/post/put/patch/delete/api_route`, `app.include_router`,
  `app.add_middleware`, `app.exception_handler`.
- MCP: `app.tool`, `app.resource`, `app.prompt`. Served at `MCP_PATH` (`/mcp`)
  as a stateless JSON route.
- CLI: `app.command("namespace:verb", lifespan=True)`. Commands run inside the
  app lifespan (database and cache open) unless `lifespan=False`.
- `app.lifespan()` is the one lifecycle used by HTTP, MCP and the CLI.
  `app.add_lifespan(factory)` adds a process-wide client to it. With
  `CACHE_DRIVER=database`, opening the cache at startup runs
  `CREATE TABLE IF NOT EXISTS` for `CACHE_TABLE`; there is no migration for it.
- `app.include_module(module)` adds a module's routers. A module with
  migration templates gets a `<name>:install` command that copies the ones the
  project doesn't have yet into `migrations/`, and a module with a schema check
  stops the server at startup with `SchemaMismatch` when its tables or columns
  are missing.
- `app.user_model`: your `BaseUser` subclass, passed as `user_model` (see
  [docs/auth.md](https://github.com/Flowmatic-AI/flowlab/blob/main/package/docs/auth.md#your-user-model)).
- `app.include_router(router, **options)` takes all three kinds of router
  (see below).

Built-in commands: `server:start`, `migrations:init|up|down|fresh|make`, `test`,
`queue:install|work|failed|retry|forget|flush|clear`.

Run the CLI with `python main.py <command>`, `flowlab <command>` or
`python -m flowlab <command>`. The last two load `main:app` from the working
directory; pick another app with `--app module:attribute` or `FLOWLAB_APP`.

## Routers

Split a project over files with one router per surface, then include each one:

```python
from flowlab import APIRouter, CommandRouter, MCPRouter

api = APIRouter(prefix="/posts")  # FastAPI's APIRouter


@api.get("/")
def posts() -> list[str]:
    return []


mcp = MCPRouter("posts")  # a FastMCP server


@mcp.tool
def count_posts() -> int:
    return 0


console = CommandRouter()


@console.command("posts:prune")
def prune() -> None:
    print("Pruned.")


app.include_router(api, tags=["posts"])  # options go to FastAPI.include_router
app.include_router(mcp, namespace="posts")  # options go to FastMCP.mount; the tool becomes posts_count_posts
app.include_router(console)
```

`flowlab` also re-exports the FastAPI names a project needs, so routes can
import from one place: `APIRouter`, `Depends`, `HTTPException`, `Request`,
`Response`, `Query`, `Path`, `Body`, `Header`, `Cookie`, `Form`, `File`,
`UploadFile`, `BackgroundTasks`, `Security`, `WebSocket`, `WebSocketDisconnect`
and `status`.

## Settings

All settings classes live in `flowlab._settings` and are exported from
`flowlab`: `FastAPISettings`, `FastMCPSettings`, `TyperSettings`,
`DatabaseSettings`, `CacheSettings`, `QueueSettings`, `AuthSettings`. They read the environment
and `.env` (from the working directory and from the directory of the script
being run).

## Modules

- `flowlab.modules.db`: query builder and ORM for SQLite,
  PostgreSQL, MySQL and MariaDB. See [docs/db.md](https://github.com/Flowmatic-AI/flowlab/blob/main/package/docs/db.md).
- `flowlab.modules.cache`: memory, database, Redis, Valkey and Memcached
  caches. See [docs/cache.md](https://github.com/Flowmatic-AI/flowlab/blob/main/package/docs/cache.md).
- `flowlab.modules.migrator`: file-based migrations, publishing templates, schema
  drop helpers. See [docs/migrator.md](https://github.com/Flowmatic-AI/flowlab/blob/main/package/docs/migrator.md).
- `flowlab.modules.auth`: users, JWT login, API keys, MCP API key auth. See
  [docs/auth.md](https://github.com/Flowmatic-AI/flowlab/blob/main/package/docs/auth.md).
- `flowlab.modules.ratelimit`: rate limits for routes and MCP tools, counted in
  the cache. See [docs/ratelimit.md](https://github.com/Flowmatic-AI/flowlab/blob/main/package/docs/ratelimit.md).
- `flowlab.modules.queue`: background jobs with `@job`, workers and failed-job
  commands, on the database, Redis or Valkey. See [docs/queue.md](https://github.com/Flowmatic-AI/flowlab/blob/main/package/docs/queue.md).

Extras: `flowlab[postgres]`, `flowlab[mysql]`, `flowlab[asyncpg]`,
`flowlab[redis]`, `flowlab[valkey]`, `flowlab[memcached]`, `flowlab[all]`.
