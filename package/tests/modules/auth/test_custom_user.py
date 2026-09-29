from collections.abc import Callable, Iterator
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from flowlab import (
    AuthNotEnabled,
    AuthSettings,
    DatabaseSettings,
    FastAPISettings,
    FastMCPSettings,
    FlowLab,
    TyperSettings,
)
from flowlab.modules.auth import BaseUser, user_model

PASSWORD = "correct horse battery staple"

JWT_SECRET = "test-suite-secret-at-least-32-bytes-long"

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

EXTRA_COLUMNS = """            .string("name", not_null=True)\\
            .string("nickname")\\
            .boolean("is_admin", not_null=True, default=False)\\
"""


class Member(BaseUser):
    __fillable__: ClassVar[tuple[str, ...]] = ("name", "nickname")

    name: str
    nickname: str | None = None
    is_admin: bool = False


def make_app(tmp_path: Path, model: type[BaseUser] = Member) -> FlowLab:
    return FlowLab(
        FastAPISettings(),
        FastMCPSettings(),
        TyperSettings(),
        database_settings=DatabaseSettings(db_driver="sqlite", db_name=str(tmp_path / "test.sqlite")),
        auth_settings=AuthSettings(jwt_secret=JWT_SECRET),
        user_model=model,
        project_dir=tmp_path,
    )


@pytest.fixture()
def app(tmp_path: Path, users_migration: Callable[[Path, str], None]) -> Iterator[FlowLab]:
    users_migration(tmp_path, EXTRA_COLUMNS)
    app = make_app(tmp_path)

    with app.lifespan():
        app.migrator.up()

    yield app


@pytest.fixture()
def client(app: FlowLab) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, **body: object) -> dict[str, object]:
    response = client.post("/auth/register", json={"email": "ada@example.com", "password": PASSWORD, **body})
    assert response.status_code == 201, response.text

    result: dict[str, object] = response.json()

    return result


def test_the_app_uses_the_supplied_model(app: FlowLab) -> None:
    assert app.user_model is Member

    with app.lifespan():
        assert user_model() is Member


def test_register_requires_and_stores_fillable_fields(client: TestClient) -> None:
    missing = client.post("/auth/register", json={"email": "ada@example.com", "password": PASSWORD})
    assert missing.status_code == 422
    assert missing.json()["detail"][0]["loc"] == ["body", "name"]

    body = register(client, name="Ada", nickname="countess")

    assert body["user"] == body["user"] | {"email": "ada@example.com", "name": "Ada", "nickname": "countess"}
    assert "password" not in body["user"]  # type: ignore[operator]


def test_register_ignores_fields_that_are_not_fillable(app: FlowLab, client: TestClient) -> None:
    body = register(client, name="Mallory", is_admin=True)

    assert body["user"]["is_admin"] is False  # type: ignore[index]

    with app.lifespan():
        stored = app.db.select_models(Member).where_equals("email", "ada@example.com").fetch_model()

    assert stored is not None
    assert stored.is_admin is False


def test_me_and_login_return_the_custom_model(client: TestClient) -> None:
    token = register(client, name="Ada")["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["name"] == "Ada"
    assert me["is_admin"] is False

    login = client.post("/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).json()
    assert login["user"]["name"] == "Ada"


def test_openapi_documents_the_custom_model_without_the_password(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert set(schemas["MemberRegistration"]["properties"]) == {"email", "password", "name", "nickname"}
    assert "name" in schemas["Member"]["properties"]
    assert "password" not in schemas["Member"]["properties"]


def test_mcp_whoami_returns_the_custom_model(client: TestClient) -> None:
    token = register(client, name="Ada")["access_token"]
    key = client.post("/api-keys", json={"name": "mcp"}, headers={"Authorization": f"Bearer {token}"}).json()["token"]

    response = client.post(
        "/mcp",
        headers=MCP_HEADERS | {"Authorization": f"Bearer {key}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "whoami", "arguments": {}}},
    )
    user = response.json()["result"]["structuredContent"]

    assert user["name"] == "Ada"
    assert "password" not in user


def test_users_create_has_an_option_per_fillable_field(app: FlowLab) -> None:
    runner = CliRunner()

    help_text = runner.invoke(app.cli, ["users:create", "--help"]).output
    assert "--name" in help_text
    assert "--nickname" in help_text
    assert "--is-admin" not in help_text

    missing = runner.invoke(app.cli, ["users:create", "--email", "bob@example.com", "--password", PASSWORD])
    assert missing.exit_code != 0

    result = runner.invoke(
        app.cli,
        ["users:create", "--email", "bob@example.com", "--name", "Bob"],
        input=f"{PASSWORD}\n{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    assert "Created user" in result.output

    with app.lifespan():
        stored = app.db.select_models(Member).where_equals("email", "bob@example.com").fetch_model()

    assert stored is not None
    assert (stored.name, stored.nickname) == ("Bob", None)


def test_fillable_may_not_name_auth_fields_or_unknown_fields(tmp_path: Path) -> None:
    class Sneaky(BaseUser):
        __fillable__: ClassVar[tuple[str, ...]] = ("password",)

    class Typo(BaseUser):
        __fillable__: ClassVar[tuple[str, ...]] = ("nmae",)

    with pytest.raises(TypeError, match="auth manages it"):
        make_app(tmp_path, Sneaky)

    assert not FlowLab.initialized()

    with pytest.raises(TypeError, match="not a field"):
        make_app(tmp_path, Typo)


def test_a_user_model_without_auth_settings_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(AuthNotEnabled):
        FlowLab(FastAPISettings(), FastMCPSettings(), TyperSettings(), user_model=Member, project_dir=tmp_path)
