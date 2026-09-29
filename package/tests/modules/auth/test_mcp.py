from typing import Any

import pytest
from fastapi.testclient import TestClient

from flowlab import FlowLab, MCPRouter
from flowlab.modules.auth import BaseUser, CurrentMCPUser

PASSWORD = "correct horse battery staple"

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client: TestClient, method: str, token: str | None, params: dict[str, Any] | None = None) -> Any:
    headers = HEADERS | ({"Authorization": f"Bearer {token}"} if token else {})
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}

    return client.post("/mcp", json=payload, headers=headers)


@pytest.fixture()
def session_token(client: TestClient, random_email: str) -> str:
    response = client.post("/auth/register", json={"email": random_email, "password": PASSWORD})

    return str(response.json()["access_token"])


@pytest.fixture()
def api_key(client: TestClient, session_token: str) -> str:
    headers = {"Authorization": f"Bearer {session_token}"}

    return str(client.post("/api-keys", json={"name": "mcp"}, headers=headers).json()["token"])


def test_mcp_without_a_key_is_401(client: TestClient) -> None:
    response = rpc(client, "tools/list", None)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


def test_mcp_rejects_a_login_token(client: TestClient, session_token: str) -> None:
    assert rpc(client, "tools/list", session_token).status_code == 401


def test_mcp_rejects_an_unknown_api_key(client: TestClient) -> None:
    assert rpc(client, "tools/list", "flk_not-a-real-key").status_code == 401


def test_whoami_returns_the_key_owner_without_the_password(client: TestClient, api_key: str, random_email: str) -> None:
    response = rpc(client, "tools/call", api_key, {"name": "whoami", "arguments": {}})

    result = response.json()["result"]

    assert result["isError"] is False
    assert result["structuredContent"]["email"] == random_email
    assert "password" not in result["structuredContent"]


def test_no_tool_schema_exposes_an_excluded_field(client: TestClient, api_key: str) -> None:
    tools = rpc(client, "tools/list", api_key).json()["result"]["tools"]

    assert "whoami" in {tool["name"] for tool in tools}
    assert all("password" not in str(tool.get("outputSchema", {})) for tool in tools)


def test_own_tools_get_the_calling_user_injected(
    app: FlowLab, client: TestClient, api_key: str, random_email: str
) -> None:
    router = MCPRouter("notes")

    @router.tool
    def my_email(shout: bool = False, user: BaseUser = CurrentMCPUser()) -> str:
        return user.email.upper() if shout else user.email

    app.include_router(router)

    tools = {tool["name"]: tool for tool in rpc(client, "tools/list", api_key).json()["result"]["tools"]}
    assert set(tools["my_email"]["inputSchema"]["properties"]) == {"shout"}

    result = rpc(client, "tools/call", api_key, {"name": "my_email", "arguments": {"shout": True}}).json()["result"]

    assert result["structuredContent"] == {"result": random_email.upper()}
