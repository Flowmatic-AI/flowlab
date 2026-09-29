# flowlab starter

An empty [flowlab](../package) project, shaped like a fresh Laravel install:
FastAPI routes, an MCP server, console commands, migrations and a custom `User` model.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # while developing the framework: pip install -e ../package
cp .env.example .env

python main.py migrations:up
python main.py users:create --email you@example.com                      # prompts for the password
python main.py server:start                                              # http://127.0.0.1:8000/docs
python main.py queue:work                                                # runs queued jobs
python main.py test
python main.py --help                                                    # every command
```

## Directory structure

| Here | Laravel | Purpose |
| --- | --- | --- |
| `main.py` | `artisan` + `bootstrap/app.php` | Creates the app, includes the three routers, runs the CLI |
| `app/models/` | `app/Models/` | Models, e.g. `User` |
| `app/jobs/` | `app/Jobs/` | Queued jobs, e.g. `welcome_user` |
| `app/dependencies.py` | `auth` middleware / `Auth::user()` | `CurrentUser` and `SessionUser`, typed as your `User` |
| `routes/api.py` | `routes/web.php` / `routes/api.php` | HTTP routes (`router`, an `APIRouter`) |
| `routes/mcp.py` | - | MCP tools (`router`, an `MCPRouter`), e.g. `dashboard` for the calling user |
| `routes/console.py` | `routes/console.php` | CLI commands (`router`, a `CommandRouter`), e.g. `inspire:quote` |
| `migrations/` | `database/migrations/` | Every schema migration, including auth's `users` and `api_keys` and the queue's `jobs` and `failed_jobs` |
| `tests/` | `tests/Feature/` | pytest tests (`python main.py test`) |
| `.env` | `.env` | Configuration, see `.env.example` |

## Queues

A job is a function decorated with `@job`, like `app/jobs/welcome.py`:

```python
from flowlab.modules.queue import job


@job(tries=3, backoff=10)
def welcome_user(user_id: int) -> None: ...


welcome_user.dispatch(user.id)          # queue it
welcome_user.later(60, user.id)         # queue it to run in a minute
```

`python main.py queue:work` runs them, with the database, cache and settings of the app. A job that raises is retried
`tries` times, `backoff` seconds apart, then lands in `queue:failed`; `queue:retry <id|all>` puts it back. Arguments
must be JSON serializable, so pass ids rather than models. Tests use `QUEUE_DRIVER=sync` (see `tests/conftest.py`),
which runs each job the moment it is dispatched.

## MCP

The MCP server is at `/mcp` and only accepts API keys, so every tool is authenticated. A tool gets the calling
user by defaulting a parameter to `CurrentMCPUser()`, as `dashboard` in `routes/mcp.py` does:

```python
@router.tool
def dashboard(user: User = CurrentMCPUser()) -> str:
    return f"Hello, {user.email}!"
```

Create a key and point an MCP client at the server:

```bash
python main.py api-keys:create --email you@example.com --name claude-code   # prints flk_... once
claude mcp add --transport http app http://127.0.0.1:8000/mcp --header "Authorization: Bearer flk_..."
```

## Customising the user model

The `users` and `api_keys` tables belong to this project; their migrations are in `migrations/`. After a flowlab
upgrade, `python main.py auth:install` adds any new auth migration without touching the ones you edited.

1. Add a field to `User` in `app/models/user.py`.
2. If users may set it at registration and in `users:create`, add it to `__fillable__`.
3. Add the column in a new migration:

```bash
python main.py migrations:make add_nickname_to_users_table
python main.py migrations:up
```
