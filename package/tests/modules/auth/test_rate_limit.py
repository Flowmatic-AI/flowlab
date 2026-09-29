from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from flowlab import APIRouter, FlowLab, MCPRouter
from flowlab._settings import AuthSettings, DatabaseSettings
from flowlab.modules.auth import MIGRATIONS_DIR
from flowlab.modules.migrator import publish_migrations
from flowlab.modules.ratelimit import MCPRateLimit, RateLimit

PASSWORD = "correct horse battery staple"

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def make_app(tmp_path: Path, jwt_secret: str, **auth: Any) -> FlowLab:
    publish_migrations(MIGRATIONS_DIR, tmp_path / "migrations")

    router = APIRouter()

    @router.get("/reports", dependencies=[RateLimit("1/minute", by="user")])
    def reports() -> str:
        return "ok"

    tools = MCPRouter("tools")

    @tools.tool
    def per_key(_: None = MCPRateLimit("1/minute")) -> str:
        return "ok"

    @tools.tool
    def per_user(_: None = MCPRateLimit("1/minute", by="user")) -> str:
        return "ok"

    app = FlowLab(
        database_settings=DatabaseSettings(db_driver="sqlite", db_name=str(tmp_path / "test.sqlite")),
        auth_settings=AuthSettings(jwt_secret=jwt_secret, **auth),
        project_dir=tmp_path,
    )
    app.include_router(router)
    app.include_router(tools)

    with app.lifespan():
        app.migrator.up()

    return app


def login(client: TestClient, email: str, password: str = PASSWORD) -> int:
    return client.post("/auth/login", json={"email": email, "password": password}).status_code


def register(client: TestClient, email: str) -> str:
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return str(response.json()["access_token"])


def api_key(client: TestClient, token: str) -> str:
    response = client.post("/api-keys", json={"name": "k"}, headers={"Authorization": f"Bearer {token}"})
    return str(response.json()["token"])


def call(client: TestClient, key: str, tool: str) -> bool:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": {}}}
    response = client.post("/mcp", json=payload, headers=HEADERS | {"Authorization": f"Bearer {key}"})
    return bool(response.json()["result"]["isError"])


def test_login_is_limited_per_email_to_five_a_minute(tmp_path: Path, jwt_secret: str, random_email: str) -> None:
    with TestClient(make_app(tmp_path, jwt_secret)) as client:
        register(client, random_email)
        statuses = [login(client, random_email, "wrong password!") for _ in range(6)]

        assert statuses == [401] * 5 + [429]
        assert login(client, random_email) == 429
        assert login(client, "someone-else@example.com") == 401


def test_the_429_carries_retry_after(tmp_path: Path, jwt_secret: str, random_email: str) -> None:
    with TestClient(make_app(tmp_path, jwt_secret, auth_rate_limit="1/minute")) as client:
        login(client, random_email, "wrong password!")
        response = client.post("/auth/login", json={"email": random_email, "password": PASSWORD})

    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= 60


def test_email_case_does_not_dodge_the_login_limit(tmp_path: Path, jwt_secret: str) -> None:
    with TestClient(make_app(tmp_path, jwt_secret, auth_rate_limit="1/minute")) as client:
        login(client, "ada@example.com", "wrong password!")

        assert login(client, "ADA@example.com", "wrong password!") == 429


def test_a_successful_login_starts_the_count_over(tmp_path: Path, jwt_secret: str, random_email: str) -> None:
    with TestClient(make_app(tmp_path, jwt_secret, auth_rate_limit="2/minute")) as client:
        register(client, random_email)
        login(client, random_email, "wrong password!")

        assert login(client, random_email) == 200
        assert [login(client, random_email, "wrong password!") for _ in range(3)] == [401, 401, 429]


def test_register_is_limited_per_ip(tmp_path: Path, jwt_secret: str) -> None:
    with TestClient(make_app(tmp_path, jwt_secret, auth_rate_limit="2/minute")) as client:
        register(client, "a@example.com")
        register(client, "b@example.com")
        response = client.post("/auth/register", json={"email": "c@example.com", "password": PASSWORD})

    assert response.status_code == 429


@pytest.mark.parametrize("off", ["none", "off", "", None])
def test_auth_rate_limit_can_be_turned_off(tmp_path: Path, jwt_secret: str, random_email: str, off: str | None) -> None:
    with TestClient(make_app(tmp_path, jwt_secret, auth_rate_limit=off)) as client:
        assert {login(client, random_email) for _ in range(8)} == {401}


def test_auth_rate_limit_must_be_a_valid_limit(jwt_secret: str) -> None:
    with pytest.raises(ValueError, match="invalid rate limit"):
        AuthSettings(jwt_secret=jwt_secret, auth_rate_limit="lots")


def test_auth_rate_limit_is_read_from_the_environment(jwt_secret: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_RATE_LIMIT", "10/5 minutes")

    assert AuthSettings(jwt_secret=jwt_secret).auth_rate_limit == "10/5 minutes"


def test_route_limit_by_user_needs_auth_and_counts_per_user(tmp_path: Path, jwt_secret: str) -> None:
    with TestClient(make_app(tmp_path, jwt_secret)) as client:
        ada = {"Authorization": f"Bearer {register(client, 'ada@example.com')}"}
        grace = {"Authorization": f"Bearer {register(client, 'grace@example.com')}"}

        assert client.get("/reports").status_code == 401
        assert client.get("/reports", headers=ada).status_code == 200
        assert client.get("/reports", headers=ada).status_code == 429
        assert client.get("/reports", headers=grace).status_code == 200


def test_tool_limit_counts_per_key_or_per_user(tmp_path: Path, jwt_secret: str) -> None:
    with TestClient(make_app(tmp_path, jwt_secret)) as client:
        token = register(client, "ada@example.com")
        first, second = api_key(client, token), api_key(client, token)

        assert call(client, first, "per_key") is False
        assert call(client, first, "per_key") is True
        assert call(client, second, "per_key") is False

        assert call(client, first, "per_user") is False
        assert call(client, second, "per_user") is True
