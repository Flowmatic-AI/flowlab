from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from flowlab import APIRouter, FlowLab, MCPRouter, Request
from flowlab.modules.ratelimit import MCPRateLimit, RateLimit

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def make_app(tmp_path: Path) -> FlowLab:
    router = APIRouter()

    @router.get("/limited", dependencies=[RateLimit("2/minute")])
    def limited() -> str:
        return "ok"

    @router.get("/other", dependencies=[RateLimit("2/minute")])
    def other() -> str:
        return "ok"

    @router.get("/shared-a", dependencies=[RateLimit("1/minute", name="shared")])
    def shared_a() -> str:
        return "ok"

    @router.get("/shared-b", dependencies=[RateLimit("1/minute", name="shared")])
    def shared_b() -> str:
        return "ok"

    @router.get("/items/{item_id}", dependencies=[RateLimit("1/minute")])
    def item(item_id: int) -> int:
        return item_id

    def tenant(request: Request) -> str:
        return request.headers.get("X-Tenant", "none")

    @router.get("/per-tenant", dependencies=[RateLimit("1/minute", by=tenant)])
    def per_tenant() -> str:
        return "ok"

    tools = MCPRouter("tools")

    @tools.tool
    def search(q: str, _: None = MCPRateLimit("2/minute")) -> str:
        return q

    @tools.tool
    def lookup(q: str, _: None = MCPRateLimit("1/minute")) -> str:
        return q

    app = FlowLab(project_dir=tmp_path)
    app.include_router(router)
    app.include_router(tools)
    return app


def call(client: TestClient, tool: str, **arguments: Any) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    return client.post("/mcp", json=payload, headers=HEADERS).json()["result"]


def test_route_limit_answers_429_with_retry_after(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        first, second, third = (client.get("/limited") for _ in range(3))

    assert (first.status_code, second.status_code, third.status_code) == (200, 200, 429)
    assert first.headers["X-RateLimit-Limit"] == "2"
    assert first.headers["X-RateLimit-Remaining"] == "1"
    assert third.headers["X-RateLimit-Remaining"] == "0"
    assert 1 <= int(third.headers["Retry-After"]) <= 60
    assert third.json()["detail"].startswith("Too many requests")


def test_routes_are_counted_separately_unless_they_share_a_name(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        client.get("/limited")
        client.get("/limited")

        assert client.get("/other").status_code == 200
        assert client.get("/shared-a").status_code == 200
        assert client.get("/shared-b").status_code == 429


def test_a_route_counts_once_for_all_its_path_parameters(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        assert client.get("/items/1").status_code == 200
        assert client.get("/items/2").status_code == 429


def test_by_a_function_of_the_request(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        assert client.get("/per-tenant", headers={"X-Tenant": "a"}).status_code == 200
        assert client.get("/per-tenant", headers={"X-Tenant": "a"}).status_code == 429
        assert client.get("/per-tenant", headers={"X-Tenant": "b"}).status_code == 200


def test_tool_limit_is_a_tool_error_and_hidden_from_the_schema(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        results = [call(client, "search", q="x") for _ in range(3)]
        listing = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=HEADERS)

    assert [result["isError"] for result in results] == [False, False, True]
    assert results[2]["content"][0]["text"].startswith("Too many requests")
    schemas = {tool["name"]: tool["inputSchema"] for tool in listing.json()["result"]["tools"]}
    assert set(schemas["search"]["properties"]) == {"q"}


def test_tools_are_counted_separately(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        call(client, "search", q="x")
        call(client, "search", q="x")

        assert call(client, "lookup", q="x")["isError"] is False
        assert call(client, "lookup", q="x")["isError"] is True
