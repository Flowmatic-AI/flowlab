from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient

from flowlab.modules.auth import User
from flowlab.modules.auth import _users as service
from flowlab.modules.auth._security import ALGORITHM
from flowlab.modules.db.database import DB

PASSWORD = "correct horse battery staple"


def register_and_get_token(client: TestClient, email: str) -> str:
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201

    return str(response.json()["access_token"])


def test_me_with_a_valid_token_returns_the_user(client: TestClient, random_email: str) -> None:
    token = register_and_get_token(client, random_email)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == random_email
    assert "password" not in response.json()


def test_me_without_a_header_is_401_not_authenticated(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["detail"] == "Not authenticated"


def test_me_with_a_malformed_token_is_401_invalid_token(client: TestClient) -> None:
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


def test_me_with_a_token_signed_by_the_wrong_secret_is_401_invalid_token(client: TestClient) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "1", "iat": now, "exp": now + timedelta(minutes=5)},
        "not-the-real-secret-but-also-at-least-32-bytes-long",
        algorithm=ALGORITHM,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


def test_me_with_an_expired_token_is_401_token_expired(client: TestClient, jwt_secret: str) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "1", "typ": "access", "iat": now - timedelta(minutes=10), "exp": now - timedelta(minutes=1)},
        jwt_secret,
        algorithm=ALGORITHM,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"


def test_me_for_a_since_soft_deleted_user_is_401(client: TestClient, db: DB, random_email: str) -> None:
    token = register_and_get_token(client, random_email)

    user = db.select_models(User).where_equals("email", random_email).fetch_model()
    assert user is not None

    service.soft_delete(db, user)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "User no longer exists"


def test_me_with_a_non_numeric_subject_is_401_invalid_token(client: TestClient, jwt_secret: str) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "abc", "typ": "access", "iat": now, "exp": now + timedelta(minutes=5)}, jwt_secret, algorithm=ALGORITHM
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


def test_the_token_lookup_compares_the_id_as_an_integer(client: TestClient, db: DB, random_email: str) -> None:
    token = client.post("/auth/register", json={"email": random_email, "password": "correct horse battery"}).json()
    rendered: list[str] = []
    select_models = db.select_models

    def spy(model: type[User]) -> object:
        query = select_models(model)
        original = query.fetch_model

        def fetch_model() -> object:
            rendered.append(query.to_sql())
            return original()

        query.fetch_model = fetch_model  # type: ignore[method-assign]
        return query

    db.select_models = spy  # type: ignore[method-assign]
    try:
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {token['access_token']}"}).status_code == 200
    finally:
        del db.select_models

    assert any('"id" = ' in sql and "cast(" not in sql.lower() for sql in rendered)
