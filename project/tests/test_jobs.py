import logging

import pytest
from fastapi.testclient import TestClient

from app.jobs import welcome_user


def test_welcome_user_greets_a_new_user(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    response = client.post("/auth/register", json={"email": "linus@example.com", "password": "correct horse battery"})
    user_id = response.json()["user"]["id"]

    with caplog.at_level(logging.INFO, logger="app.jobs.welcome"):
        welcome_user.dispatch(user_id)

    assert "Welcome, linus@example.com!" in caplog.text
