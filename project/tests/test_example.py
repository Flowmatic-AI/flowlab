import main
from fastapi.testclient import TestClient
from typer.testing import CliRunner

PASSWORD = "correct horse battery staple"


def test_welcome(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello world"}


def test_register_and_me(client: TestClient) -> None:
    response = client.post("/auth/register", json={"email": "ada@example.com", "password": PASSWORD})

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "ada@example.com"

    token = response.json()["access_token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json() == {"email": "ada@example.com"}
    assert client.get("/me").status_code == 401


def test_inspire_quote() -> None:
    result = CliRunner().invoke(main.app.cli, ["inspire:quote"])

    assert result.exit_code == 0
    assert result.output.strip()


def test_mcp_dashboard_knows_the_calling_user(client: TestClient) -> None:
    session = client.post("/auth/register", json={"email": "grace@example.com", "password": PASSWORD}).json()
    api_key = client.post(
        "/api-keys", json={"name": "tests"}, headers={"Authorization": f"Bearer {session['access_token']}"}
    ).json()["token"]

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "dashboard", "arguments": {}}},
        headers={"Accept": "application/json, text/event-stream", "Authorization": f"Bearer {api_key}"},
    )

    assert response.json()["result"]["structuredContent"] == {"result": "Hello, grace@example.com!"}
    assert client.post("/mcp", json={}, headers={"Accept": "application/json, text/event-stream"}).status_code == 401
