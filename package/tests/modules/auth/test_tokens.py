from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from flowlab.modules.auth import TokenInvalid, decode_token, mint_token
from flowlab.modules.auth._security import ALGORITHM

PASSWORD = "correct horse battery staple"


def register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201

    return dict(response.json())


def test_a_token_of_another_type_for_the_same_id_is_not_a_login(client: TestClient, random_email: str) -> None:
    user = register(client, random_email)["user"]
    assert isinstance(user, dict)
    participant_token = mint_token(str(user["id"]), typ="participant")

    for path in ("/auth/me", "/api-keys"):
        response = client.get(path, headers={"Authorization": f"Bearer {participant_token}"})

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid token"


def test_a_token_without_a_type_is_not_a_login(client: TestClient, jwt_secret: str, random_email: str) -> None:
    user = register(client, random_email)["user"]
    assert isinstance(user, dict)
    now = datetime.now(UTC)
    untyped = jwt.encode(
        {"sub": str(user["id"]), "iat": now, "exp": now + timedelta(minutes=5)}, jwt_secret, algorithm=ALGORITHM
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {untyped}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


def test_decode_token_only_accepts_the_type_it_is_asked_for(client: TestClient) -> None:
    token = mint_token("42", typ="participant", ttl=timedelta(minutes=5))

    assert decode_token(token, typ="participant")["sub"] == "42"

    with pytest.raises(TokenInvalid):
        decode_token(token)

    with pytest.raises(TokenInvalid):
        decode_token(mint_token("42"), typ="participant")


def test_login_tokens_carry_the_access_type(client: TestClient, jwt_secret: str, random_email: str) -> None:
    token = register(client, random_email)["access_token"]
    assert isinstance(token, str)

    assert jwt.decode(token, jwt_secret, algorithms=[ALGORITHM])["typ"] == "access"
