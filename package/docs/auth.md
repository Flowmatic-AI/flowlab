# Auth

Users, JWT login, API keys and MCP authentication as a FlowLab module.

```python
from flowlab import AuthSettings, FlowLab

app = FlowLab(auth_settings=AuthSettings())
```

Passing `auth_settings` turns auth on: the app registers the routers, the `auth` MCP server, the `users:create`,
`api-keys:create` and `auth:install` commands, and the MCP auth provider. `AuthSettings()` reads `JWT_SECRET` / `JWT_TTL_MINUTES` from the
environment, so a missing `JWT_SECRET` fails at boot.

## Your user model

The user model belongs to the project, like Laravel's `app/Models/User.php`. Subclass `BaseUser` and pass it as
`user_model`; without one the app uses `flowlab.modules.auth.User`, which adds nothing to `BaseUser`.

```python
from typing import ClassVar

from flowlab.modules.auth import BaseUser


class User(BaseUser):
    __fillable__: ClassVar[tuple[str, ...]] = ("name",)

    name: str
    is_admin: bool = False


app = FlowLab(..., auth_settings=AuthSettings(), user_model=User)
```

- `BaseUser` has the fields auth relies on: `id`, `email`, `password` (never serialized), `created_at`,
  `updated_at` and `deleted_at`, on the `users` table. Override `__table__` to use another table.
- **`__fillable__`** (Laravel's `$fillable`) lists the extra fields a new user may set. `POST /auth/register`
  accepts exactly `email`, `password` and those fields, validated with the model's own annotations and defaults, and
  `users:create` gets one `--<field>` option per fillable field. A field that is not fillable (`is_admin` above) keeps
  its default on registration, whatever the request sends. Listing an auth field (`password`, `email`, ...) or a name
  that is not a field raises `TypeError` at boot.
- `GET /auth/me`, the `user` in login and register responses, the MCP `whoami` tool and the OpenAPI schema all use your
  model. `Auth` / `SessionAuth` are typed as `BaseUser`; for your own type in a route, declare
  `CurrentUser = Annotated[User, Depends(get_user)]` with `get_user` (or `get_session_user`) from
  `flowlab.modules.auth`.
- `app.user_model` and `flowlab.modules.auth.user_model()` return the model in use.
- Passing `user_model` without `auth_settings` raises `AuthNotEnabled`.

## Settings

| Env var | Default | Meaning |
| --- | --- | --- |
| `JWT_SECRET` | required | HS256 signing secret (use 32+ bytes) |
| `JWT_TTL_MINUTES` | `60` | login token lifetime |
| `AUTH_RATE_LIMIT` | `5/minute` | login and register attempts, like `10/5 minutes`; `none` turns it off |

`auth.get_auth_settings()` returns `FlowLab.instance().auth`. It raises `FlowLabNotInitialized` before an app exists and
`AuthNotEnabled` when the app was created without `auth_settings`.

## Endpoints

| Method and path | Auth | Result |
| --- | --- | --- |
| `POST /auth/register` | none | 201 `{access_token, token_type, user}`; 409 on a taken email; 422 on a bad email, a password under 8 characters or over 72 bytes; 429 over `AUTH_RATE_LIMIT` |
| `POST /auth/login` | none | `{access_token, token_type, user}`; 401 "Incorrect email or password" for both unknown email and wrong password; 429 over `AUTH_RATE_LIMIT` |
| `GET /auth/me` | `Auth` | the current user (the password is never serialized) |
| `POST /api-keys` | `SessionAuth` | 201 `{api_key, token}`; the token is shown once |
| `GET /api-keys` | `SessionAuth` | your live keys, newest first |
| `DELETE /api-keys/{id}` | `SessionAuth` | 204; another user's key is 404, not 403 |

## Auth vs SessionAuth

A bearer credential is a login JWT or an API key (prefix `flk_`).

- `Auth` accepts either. Use it on every protected route.
- `SessionAuth` accepts a JWT only. Use it for anything a leaked key must not do (managing API keys).

```python
from flowlab.modules.auth import Auth, User


@app.get("/things")
def things(user: Auth) -> list[str]: ...
```

Failures are 401 with `WWW-Authenticate: Bearer`.

## Rate limiting

Login and register are rate limited with `AUTH_RATE_LIMIT` (default 5 a minute). Login counts per client address plus
email, and a successful login starts the count over; register counts per address. Over the limit is a 429 with
`Retry-After`. To limit your own routes and tools, see [ratelimit.md](ratelimit.md).

## API keys

- Format `flk_` + 32 random urlsafe bytes. Stored as a SHA-256 hash (`token_hash`, excluded from serialization) plus a
  `hint` (prefix and 8 characters).
- Revoking is a soft delete (`deleted_at`); users are soft-deleted too, which also disables their keys.
- Passwords use bcrypt with the 72-byte limit checked on encoded bytes. Login burns a dummy bcrypt check for unknown
  emails to keep timing flat.

## MCP

The module sets `ApiKeyVerifier` as the MCP auth provider: `/mcp` accepts API keys only; a JWT or no token is 401.
Every MCP tool is therefore authenticated. The module also ships an `auth` MCP server with a `whoami` tool.

To get the user who owns the calling key in your own tool, give it a parameter defaulting to `CurrentMCPUser()`,
the MCP counterpart of the `CurrentUser` route dependency:

```python
from app.models import User
from flowlab import MCPRouter
from flowlab.modules.auth import CurrentMCPUser

router = MCPRouter("app")


@router.tool
def dashboard(user: User = CurrentMCPUser()) -> str:
    return f"Hello, {user.email}!"
```

The parameter is filled in by the server and left out of the tool's input schema, so MCP clients never see it. The
user is an instance of your user model; a key whose user was deleted gets a "User no longer exists" tool error.
FastMCP only injects dependencies declared as parameter defaults, so `Annotated[User, ...]` does not work here as it
does for routes. `CurrentMCPUser()` is built on FastMCP's `Depends`, which `flowlab` re-exports as `MCPDepends` for
your own MCP dependencies. `get_mcp_user()` returns the same user without injection, and `current_user(db)` takes an
explicit database.

Calling a tool needs an API key: create one with `POST /api-keys` or `python main.py api-keys:create`, then send it
as `Authorization: Bearer flk_...`.

## Commands

```
users:create --email a@b.co [--<fillable field> ...] [--password ...]   # prompts for the password when omitted
api-keys:create --email a@b.co --name claude-code # prints the token once
```

## Migrations

**Auth's tables are the project's**, as in Laravel. The package ships migration templates, and `auth:install` copies
the ones the project doesn't have yet into its `migrations/`:

- `0001_01_01_000000_create_users_table.py`: `id` (auto increment), `email` (string, unique), `password` (string),
  `created_at` / `updated_at` (`current_timestamp`) and `deleted_at` (datetime). Add a column for each extra field
  on your user model, in this file before the first `migrations:up` or in a new migration after it.
- `0001_01_01_000001_create_api_keys_table.py`: API keys, with a foreign key to `users.id`.

```bash
python main.py auth:install     # prints "Published <file>" for each new file
python main.py migrations:up
```

A file is only copied when the project has no migration with that name, so edits to published files are safe. When a
later flowlab version needs a schema change, it ships a new template: run `auth:install` again to pick it up.

**The server checks the schema at startup.** If the `users` or `api_keys` table is missing, or a field on your user
model has no column, the app refuses to start with `SchemaMismatch`, which names what's missing, instead of failing
later on the first query. The message says what fixes it: `auth:install` for a missing table (or a column one of
flowlab's own migrations adds), a migration of your own for a field you added to your user model. CLI commands skip the check, so `auth:install` and `migrations:up` still work on an empty
database.

## Public API

`module`, `BaseUser`, `User`, `user_model`, `Auth`, `SessionAuth`, `get_user`, `get_session_user`, `ApiKey`,
`CurrentMCPUser`, `get_mcp_user`, `current_user`, `ApiKeyVerifier`, `get_auth_settings`.
