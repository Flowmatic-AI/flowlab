from pathlib import Path

from fastapi.testclient import TestClient

from flowlab import FlowLab
from flowlab._settings import AuthSettings, DatabaseSettings, FastAPISettings, FastMCPSettings, TyperSettings
from flowlab.modules.auth import MIGRATIONS_DIR, User
from flowlab.modules.auth import _users as service
from flowlab.modules.db.database import DB
from flowlab.modules.migrator import publish_migrations

PASSWORD = "correct horse battery staple"


def test_register_returns_a_token_and_normalizes_the_email(client: TestClient, random_email: str) -> None:
    response = client.post(
        "/auth/register",
        json={"email": f"  {random_email.upper()}  ", "password": PASSWORD},
    )

    assert response.status_code == 201

    body = response.json()

    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert body["user"]["email"] == random_email
    assert "password" not in body["user"]
    assert "password" not in body


def test_register_duplicate_email_is_409(client: TestClient, random_email: str) -> None:
    payload = {"email": random_email, "password": PASSWORD}

    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_register_soft_deleted_email_is_409_not_500(client: TestClient, db: DB, random_email: str) -> None:
    assert client.post("/auth/register", json={"email": random_email, "password": PASSWORD}).status_code == 201

    user = db.select_models(User).where_equals("email", random_email).fetch_model()
    assert user is not None

    service.soft_delete(db, user)

    response = client.post("/auth/register", json={"email": random_email, "password": PASSWORD})

    assert response.status_code == 409


def test_soft_delete_bumps_updated_at(client: TestClient, db: DB, random_email: str) -> None:
    assert client.post("/auth/register", json={"email": random_email, "password": PASSWORD}).status_code == 201

    user = db.select_models(User).where_equals("email", random_email).fetch_model()
    assert user is not None

    service.soft_delete(db, user)

    stored = db.select_models(User).where_equals("id", user.id).fetch_model()
    assert stored is not None
    assert stored.deleted_at is not None
    assert stored.updated_at == stored.deleted_at


def test_register_password_over_the_byte_limit_is_422(client: TestClient, random_email: str) -> None:
    response = client.post("/auth/register", json={"email": random_email, "password": "é" * 40})

    assert response.status_code == 422


def test_register_password_too_short_is_422(client: TestClient, random_email: str) -> None:
    response = client.post("/auth/register", json={"email": random_email, "password": "short1"})

    assert response.status_code == 422


def test_register_invalid_email_is_422(client: TestClient) -> None:
    response = client.post("/auth/register", json={"email": "not-an-email", "password": PASSWORD})

    assert response.status_code == 422


def test_registration_can_be_turned_off(tmp_path: Path, jwt_secret: str, random_email: str) -> None:
    publish_migrations(MIGRATIONS_DIR, tmp_path / "migrations")
    app = FlowLab(
        FastAPISettings(),
        FastMCPSettings(),
        TyperSettings(),
        database_settings=DatabaseSettings(db_driver="sqlite", db_name=str(tmp_path / "test.sqlite")),
        auth_settings=AuthSettings(jwt_secret=jwt_secret, auth_registration=False),
        project_dir=tmp_path,
    )

    with app.lifespan():
        app.migrator.up()

    with TestClient(app) as client:
        response = client.post("/auth/register", json={"email": random_email, "password": PASSWORD})

        assert response.status_code == 404
        assert "/auth/register" not in client.get("/openapi.json").json()["paths"]
        assert client.post("/auth/login", json={"email": random_email, "password": PASSWORD}).status_code == 401
