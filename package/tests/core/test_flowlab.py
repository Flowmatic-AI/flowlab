from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from flowlab import (
    DB,
    AppEnv,
    AuthNotEnabled,
    AuthSettings,
    Cache,
    CacheDriver,
    CacheSettings,
    DatabaseSettings,
    FastAPISettings,
    FastMCPSettings,
    FlowLab,
    FlowLabAlreadyInitialized,
    FlowLabNotInitialized,
    NotConnected,
    TyperSettings,
    get_app,
    get_cache,
    get_db,
)
from flowlab._console import load_app
from flowlab.modules.migrator import ForeignKeyCycle, drop_order

MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def make_app(tmp_path: Path, **fastapi: object) -> FlowLab:
    return FlowLab(
        FastAPISettings(**fastapi),
        FastMCPSettings(),
        TyperSettings(),
        database_settings=DatabaseSettings(db_driver="sqlite", db_name="test.sqlite"),
        cache_settings=CacheSettings(cache_driver="memory"),
        project_dir=tmp_path,
    )


def call_tool(client: TestClient, name: str, arguments: dict[str, object]) -> dict[str, object]:
    response = client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
    )
    assert response.status_code == 200

    result: dict[str, object] = response.json()["result"]

    return result


def test_serves_routes_health_and_mcp(tmp_path: Path) -> None:
    app = make_app(tmp_path)

    @app.get("/hello")
    def hello(db: DB, cache: Cache) -> dict[str, object]:
        return {"tables": db.list_tables(), "value": cache.remember("key", lambda: 42)}

    @app.tool
    def add(a: int, b: int) -> int:
        return a + b

    with TestClient(app) as client:
        assert client.get("/health").json() == {"database": True}
        assert client.get("/hello").json() == {"tables": [], "value": 42}
        assert call_tool(client, "add", {"a": 2, "b": 3})["structuredContent"] == {"result": 5}


def test_mcp_is_a_route_not_a_redirecting_mount(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        response = client.post("/mcp", headers=MCP_HEADERS, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response.status_code == 200
    assert response.json()["result"]["tools"] == []


def test_sqlite_path_resolves_against_the_project_dir(tmp_path: Path) -> None:
    with make_app(tmp_path).lifespan():
        get_db().list_tables()

    assert (tmp_path / "test.sqlite").exists()


def test_lifespan_opens_and_closes_db_and_cache(tmp_path: Path) -> None:
    app = make_app(tmp_path)

    with app.lifespan():
        get_db()
        get_cache()

    with pytest.raises(RuntimeError):
        get_db()

    with pytest.raises(RuntimeError):
        get_cache()


def test_add_lifespan_runs_inside_the_core_lifespan(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    events: list[str] = []

    from contextlib import contextmanager

    @contextmanager
    def client():  # type: ignore[no-untyped-def]
        get_db()
        events.append("open")
        yield
        events.append("close")

    app.add_lifespan(client)

    with app.lifespan():
        assert events == ["open"]

    assert events == ["open", "close"]


def test_commands_run_inside_the_lifespan_unless_opted_out(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    seen: dict[str, bool] = {}

    def has_db() -> bool:
        try:
            get_db()
        except RuntimeError:
            return False

        return True

    @app.command("probe:inside")
    def inside() -> None:
        seen["inside"] = has_db()

    @app.command("probe:outside", lifespan=False)
    def outside() -> None:
        seen["outside"] = has_db()

    runner = CliRunner()
    assert runner.invoke(app.cli, ["probe:inside"]).exit_code == 0
    assert runner.invoke(app.cli, ["probe:outside"]).exit_code == 0
    assert seen == {"inside": True, "outside": False}


def test_core_commands_are_registered(tmp_path: Path) -> None:
    names = {command.name for command in make_app(tmp_path).cli.registered_commands}

    assert names == {
        "server:start",
        "migrations:init",
        "migrations:up",
        "migrations:down",
        "migrations:fresh",
        "migrations:make",
        "test",
        "queue:install",
        "queue:work",
        "queue:failed",
        "queue:retry",
        "queue:forget",
        "queue:flush",
        "queue:clear",
    }


def test_migrations_make_up_fresh_and_down(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    runner = CliRunner()

    made = runner.invoke(app.cli, ["migrations:make", "create_posts_table"])
    assert made.exit_code == 0, made.output

    path = Path(made.output.strip())
    assert path.parent == tmp_path / "migrations"

    path.write_text(
        "from flowlab.modules.migrator import MigrationABC\n\n\n"
        "class CreatePostsTable(MigrationABC):\n"
        "    def up(self, db):\n"
        "        db.create_table('posts').auto_increment('id').text('title').execute()\n\n"
        "    def down(self, db):\n"
        "        db.drop_table('posts').execute()\n"
    )

    assert runner.invoke(app.cli, ["migrations:up"]).exit_code == 0

    with app.lifespan():
        assert set(get_db().list_tables()) == {"posts", "migrations"}

    fresh = runner.invoke(app.cli, ["migrations:fresh"])
    assert fresh.exit_code == 0, fresh.output
    assert "Dropped posts" in fresh.output

    assert runner.invoke(app.cli, ["migrations:down"]).exit_code == 0

    with app.lifespan():
        assert set(get_db().list_tables()) == {"migrations"}


def test_migrations_fresh_refuses_in_production_without_force(tmp_path: Path) -> None:
    app = make_app(tmp_path, app_env="production")

    result = CliRunner().invoke(app.cli, ["migrations:fresh"])

    assert result.exit_code == 1


def test_production_hides_docs_and_tracebacks(tmp_path: Path) -> None:
    app = make_app(tmp_path, app_env=AppEnv.PRODUCTION)

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("secret detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/boom").json() == {"detail": "Internal server error"}


def test_local_shows_docs_and_tracebacks(tmp_path: Path) -> None:
    app = make_app(tmp_path)

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("visible detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/docs").status_code == 200
        body = client.get("/boom").json()

    assert body["error"] == "ValueError"
    assert body["detail"] == "visible detail"


def test_fastapi_kwargs_pass_through(tmp_path: Path) -> None:
    app = FlowLab(FastAPISettings(), FastMCPSettings(), TyperSettings(), project_dir=tmp_path, version="9.9.9")

    assert app.api.version == "9.9.9"


def test_project_dir_defaults_to_the_calling_file() -> None:
    app = FlowLab(FastAPISettings(), FastMCPSettings(), TyperSettings())

    assert app.project_dir == Path(__file__).resolve().parent
    assert get_app() is app


def test_settings_normalize_and_default() -> None:
    assert FastAPISettings(app_env=" PRODUCTION ").cors_origins == []
    assert FastAPISettings(app_env="local").cors_origins == ["*"]
    assert DatabaseSettings(db_driver="postgres").db_port == 5432
    assert CacheSettings(cache_driver="Redis").cache_driver is CacheDriver.REDIS
    assert CacheSettings(cache_driver="redis").cache_port == 6379


def test_console_loads_main_app_from_the_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "entry_for_console_test.py").write_text(
        "from flowlab import FastAPISettings, FastMCPSettings, FlowLab, TyperSettings\n"
        "app = FlowLab(FastAPISettings(), FastMCPSettings(), TyperSettings())\n"
    )
    monkeypatch.chdir(tmp_path)

    app = load_app("entry_for_console_test:app")

    assert app.project_dir == tmp_path.resolve()
    assert app._import_string() == "entry_for_console_test:app"


def test_drop_order_puts_children_first_and_rejects_cycles() -> None:
    assert drop_order({"users": set(), "posts": {"users"}}) == ["posts", "users"]

    with pytest.raises(ForeignKeyCycle):
        drop_order({"a": {"b"}, "b": {"a"}})


def test_nothing_works_before_an_app_is_initialized() -> None:
    assert not FlowLab.initialized()

    with pytest.raises(FlowLabNotInitialized):
        FlowLab.instance()

    with pytest.raises(FlowLabNotInitialized):
        get_app()

    with pytest.raises(FlowLabNotInitialized):
        get_db()

    with pytest.raises(FlowLabNotInitialized):
        get_cache()


def test_there_is_only_one_app(tmp_path: Path) -> None:
    app = make_app(tmp_path)

    assert FlowLab.instance() is app
    assert get_app() is app

    with pytest.raises(FlowLabAlreadyInitialized):
        make_app(tmp_path)

    assert FlowLab.instance() is app


def test_a_failed_init_leaves_no_app_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(self: FlowLab, router: object, **options: object) -> None:
        raise ValueError("boom")

    monkeypatch.setattr(FlowLab, "include_router", fail)

    with pytest.raises(ValueError, match="boom"):
        make_app(tmp_path)

    assert not FlowLab.initialized()


def test_reset_closes_connections_and_forgets_the_app(tmp_path: Path) -> None:
    app = make_app(tmp_path)

    with app.lifespan():
        FlowLab.reset()

        with pytest.raises(NotConnected):
            _ = app.db

    assert not FlowLab.initialized()
    make_app(tmp_path)


def test_db_cache_and_migrator_live_on_the_app(tmp_path: Path) -> None:
    app = make_app(tmp_path)

    with pytest.raises(NotConnected):
        _ = app.db

    with pytest.raises(NotConnected):
        _ = app.cache

    with pytest.raises(NotConnected):
        _ = app.migrator

    with app.lifespan():
        assert get_db() is app.db
        assert get_cache() is app.cache

        app.migrator.up()
        assert "migrations" in app.db.list_tables()

        with app.lifespan():
            assert get_db() is app.db

        app.db.list_tables()


def test_auth_is_off_unless_configured(tmp_path: Path) -> None:
    app = make_app(tmp_path)

    with pytest.raises(AuthNotEnabled):
        _ = app.auth

    from flowlab.modules import auth

    with pytest.raises(AuthNotEnabled):
        app.include_module(auth.module())


def test_auth_settings_turn_auth_on(tmp_path: Path) -> None:
    app = FlowLab(
        FastAPISettings(),
        FastMCPSettings(),
        TyperSettings(),
        auth_settings=AuthSettings(jwt_secret="x" * 32),
        project_dir=tmp_path,
    )

    assert app.auth.jwt_secret == "x" * 32
    assert {"users:create", "api-keys:create", "auth:install"} <= {
        command.name for command in app.cli.registered_commands
    }

    runner = CliRunner()
    installed = runner.invoke(app.cli, ["auth:install"])
    assert installed.exit_code == 0, installed.output
    assert sorted(path.name for path in (tmp_path / "migrations").iterdir()) == [
        "0001_01_01_000000_create_users_table.py",
        "0001_01_01_000001_create_api_keys_table.py",
    ]
    assert "already in this project" in runner.invoke(app.cli, ["auth:install"]).output
    assert runner.invoke(app.cli, ["migrations:up"]).exit_code == 0

    with TestClient(app) as client:
        assert client.post("/auth/login", json={}).status_code == 422


def test_reload_target_reuses_the_app_or_imports_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from flowlab._console import RELOAD_TARGET_ENV, reload_target

    (tmp_path / "entry_for_reload_test.py").write_text(
        "from flowlab import FastAPISettings, FastMCPSettings, FlowLab, TyperSettings\n"
        "app = FlowLab(FastAPISettings(), FastMCPSettings(), TyperSettings())\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(RELOAD_TARGET_ENV, "entry_for_reload_test:app")

    imported = reload_target()

    assert imported is FlowLab.instance()
    assert reload_target() is imported


def test_database_cache_creates_its_table_at_startup_without_a_migration(tmp_path: Path) -> None:
    app = FlowLab(
        FastAPISettings(),
        FastMCPSettings(),
        TyperSettings(),
        database_settings=DatabaseSettings(db_driver="sqlite", db_name="test.sqlite"),
        cache_settings=CacheSettings(cache_driver="database", cache_table="app_cache"),
        project_dir=tmp_path,
    )

    with app.lifespan():
        assert "app_cache" in app.db.list_tables()

        app.cache.set("key", {"value": 1})
        assert app.cache.get("key") == {"value": 1}

    with app.lifespan():
        assert app.cache.get("key") == {"value": 1}


def test_database_cache_table_is_recreated_on_the_next_start_after_migrations_fresh(tmp_path: Path) -> None:
    app = FlowLab(
        FastAPISettings(),
        FastMCPSettings(),
        TyperSettings(),
        database_settings=DatabaseSettings(db_driver="sqlite", db_name="test.sqlite"),
        cache_settings=CacheSettings(cache_driver="database"),
        project_dir=tmp_path,
    )

    assert CliRunner().invoke(app.cli, ["migrations:fresh"]).exit_code == 0

    with app.lifespan():
        assert "cache" in app.db.list_tables()


def test_auth_settings_require_a_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ValidationError, match="JWT_SECRET is required"):
        AuthSettings(_env_file=None, jwt_secret="")

    with pytest.raises(ValidationError, match="JWT_SECRET is required"):
        AuthSettings(_env_file=None, jwt_secret="   ")


def test_settings_default_when_omitted(tmp_path: Path) -> None:
    app = FlowLab(project_dir=tmp_path)

    assert isinstance(app.fastapi_settings, FastAPISettings)
    assert isinstance(app.fastmcp_settings, FastMCPSettings)
    assert isinstance(app.typer_settings, TyperSettings)


def test_include_router_takes_api_mcp_and_command_routers(tmp_path: Path) -> None:
    from flowlab import APIRouter, CommandRouter, MCPRouter

    app = make_app(tmp_path)
    api, mcp, commands = APIRouter(prefix="/greetings"), MCPRouter(), CommandRouter()
    ran: list[str] = []

    @api.get("/hi")
    def hi() -> dict[str, str]:
        return {"message": "hi"}

    @mcp.tool
    def shout(text: str) -> str:
        return text.upper()

    @commands.command("greet:wave")
    def wave() -> None:
        ran.append("wave")

    app.include_router(api, tags=["greetings"])
    app.include_router(mcp, namespace="text")
    app.include_router(commands)

    with TestClient(app) as client:
        assert client.get("/greetings/hi").json() == {"message": "hi"}
        assert call_tool(client, "text_shout", {"text": "hey"})["structuredContent"] == {"result": "HEY"}

    assert CliRunner().invoke(app.cli, ["greet:wave"]).exit_code == 0
    assert ran == ["wave"]

    with pytest.raises(TypeError):
        app.include_router(commands, prefix="/nope")

    with pytest.raises(TypeError):
        app.include_router(object())  # type: ignore[arg-type]


def test_the_package_runs_as_a_module_and_has_a_version() -> None:
    import subprocess
    import sys

    import flowlab

    assert flowlab.__version__ != "0.0.0"

    result = subprocess.run(
        [sys.executable, "-m", "flowlab", "--app", "missing_module_for_test:app"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "missing_module_for_test" in result.stderr


def test_auth_refuses_to_start_without_its_tables(tmp_path: Path) -> None:
    from flowlab import SchemaMismatch

    app = FlowLab(auth_settings=AuthSettings(jwt_secret="x" * 32), project_dir=tmp_path)

    with pytest.raises(SchemaMismatch, match=r"table users, table api_keys\. Run `auth:install`"), TestClient(app):
        pass


def test_auth_refuses_to_start_when_the_user_model_has_an_unmigrated_column(tmp_path: Path) -> None:
    from flowlab import SchemaMismatch
    from flowlab.modules.auth import BaseUser

    class Member(BaseUser):
        nickname: str | None = None

    app = FlowLab(auth_settings=AuthSettings(jwt_secret="x" * 32), user_model=Member, project_dir=tmp_path)
    runner = CliRunner()
    runner.invoke(app.cli, ["auth:install"])
    assert runner.invoke(app.cli, ["migrations:up"]).exit_code == 0

    with pytest.raises(SchemaMismatch, match=r"column users\.nickname") as error, TestClient(app):
        pass

    assert "migration of your own" in str(error.value)
    assert "auth:install" not in str(error.value)


def test_an_outdated_api_keys_table_points_at_auth_install(tmp_path: Path) -> None:
    from flowlab import SchemaMismatch

    app = FlowLab(auth_settings=AuthSettings(jwt_secret="x" * 32), project_dir=tmp_path)
    runner = CliRunner()
    runner.invoke(app.cli, ["auth:install"])
    assert runner.invoke(app.cli, ["migrations:up"]).exit_code == 0

    with app.lifespan():
        app.db.alter_table("api_keys").drop_column("hint").execute()

    with pytest.raises(SchemaMismatch, match=r"column api_keys\.hint\. Run `auth:install`"), TestClient(app):
        pass


def test_every_built_in_command_has_a_help_summary(tmp_path: Path) -> None:
    app = FlowLab(auth_settings=AuthSettings(jwt_secret="x" * 32), project_dir=tmp_path)
    listing = CliRunner().invoke(app.cli, ["--help"], terminal_width=200).output
    summaries = {line.split()[0]: line.split()[1:] for line in listing.splitlines() if line.startswith("  ")}
    built_in = {command.name for command in app.cli.registered_commands}

    assert {"server:start", "migrations:up", "test", "users:create", "queue:work"} <= built_in
    assert sorted(name for name in built_in if not summaries.get(name)) == []
