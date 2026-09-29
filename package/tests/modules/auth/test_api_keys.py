import pytest
from fastapi.testclient import TestClient

from flowlab.modules.auth import ApiKey
from flowlab.modules.auth._security import API_KEY_PREFIX, hash_api_key
from flowlab.modules.db import DB

PASSWORD = "correct horse battery staple"


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201

    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_key(client: TestClient, session: dict[str, str], name: str = "claude-code") -> dict[str, object]:
    response = client.post("/api-keys", json={"name": name}, headers=session)
    assert response.status_code == 201

    body: dict[str, object] = response.json()

    return body


@pytest.fixture()
def session(client: TestClient, random_email: str) -> dict[str, str]:
    return login(client, random_email)


def test_creating_a_key_returns_the_token_once_and_stores_only_its_hash(
    client: TestClient, db: DB, session: dict[str, str]
) -> None:
    body = create_key(client, session, name="  claude-code  ")
    token = str(body["token"])
    api_key = body["api_key"]

    assert isinstance(api_key, dict)
    assert token.startswith(API_KEY_PREFIX)
    assert api_key["name"] == "claude-code"
    assert token.startswith(api_key["hint"])
    assert "token_hash" not in api_key

    stored = db.select_models(ApiKey).where_equals("id", api_key["id"]).fetch_model()
    assert stored is not None
    assert stored.token_hash == hash_api_key(token)
    assert token not in stored.model_dump_json()


def test_an_api_key_authenticates_like_a_login_token(
    client: TestClient, session: dict[str, str], random_email: str
) -> None:
    token = create_key(client, session)["token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == random_email


def test_an_unknown_api_key_is_401(client: TestClient) -> None:
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {API_KEY_PREFIX}not-a-real-key"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


def test_a_revoked_api_key_stops_working(client: TestClient, session: dict[str, str]) -> None:
    body = create_key(client, session)
    api_key = body["api_key"]
    assert isinstance(api_key, dict)

    assert client.delete(f"/api-keys/{api_key['id']}", headers=session).status_code == 204

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})

    assert response.status_code == 401


def test_listing_shows_only_the_callers_live_keys_newest_first(
    client: TestClient, session: dict[str, str], random_email: str
) -> None:
    other = login(client, f"other-{random_email}")
    create_key(client, other)

    for index in range(3):
        create_key(client, session, name=f"key-{index}")

    revoked = create_key(client, session, name="revoked")["api_key"]
    assert isinstance(revoked, dict)
    client.delete(f"/api-keys/{revoked['id']}", headers=session)

    response = client.get("/api-keys", headers=session)

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["key-2", "key-1", "key-0"]


def test_revoking_someone_elses_key_is_404(client: TestClient, session: dict[str, str], random_email: str) -> None:
    other = login(client, f"other-{random_email}")
    api_key = create_key(client, other)["api_key"]
    assert isinstance(api_key, dict)

    assert client.delete(f"/api-keys/{api_key['id']}", headers=session).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/api-keys"), ("get", "/api-keys"), ("delete", "/api-keys/1")],
)
def test_an_api_key_cannot_manage_api_keys(client: TestClient, session: dict[str, str], method: str, path: str) -> None:
    token = create_key(client, session)["token"]

    response = client.request(method, path, json={"name": "minted"}, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_a_blank_name_is_422(client: TestClient, session: dict[str, str]) -> None:
    assert client.post("/api-keys", json={"name": "   "}, headers=session).status_code == 422
