from fastapi.testclient import TestClient

PASSWORD = "correct horse battery staple"


def register(client: TestClient, email: str) -> None:
    response = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201


def test_login_with_correct_credentials_returns_a_token(client: TestClient, random_email: str) -> None:
    register(client, random_email)

    response = client.post("/auth/login", json={"email": random_email, "password": PASSWORD})

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]


def test_login_with_unknown_email_is_401(client: TestClient, random_email: str) -> None:
    response = client.post("/auth/login", json={"email": random_email, "password": PASSWORD})

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_login_with_wrong_password_is_401_with_the_same_message(client: TestClient, random_email: str) -> None:
    register(client, random_email)

    response = client.post("/auth/login", json={"email": random_email, "password": "not the password"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"
