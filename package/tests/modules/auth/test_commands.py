from typer.testing import CliRunner

from flowlab import FlowLab
from flowlab._database import get_db
from flowlab.modules.auth import ApiKey, User
from flowlab.modules.auth._security import hash_api_key, verify_password
from flowlab.modules.db import DB

PASSWORD = "correct horse battery staple"

runner = CliRunner()


def test_users_create_stores_a_hashed_user(app: FlowLab) -> None:
    result = runner.invoke(app.cli, ["users:create", "--email", "  CLI@Example.com ", "--password", PASSWORD])

    assert result.exit_code == 0, result.output
    assert "cli@example.com" in result.output

    with app.lifespan():
        user = get_db().select_models(User).where_equals("email", "cli@example.com").fetch_model()

    assert user is not None
    assert user.password != PASSWORD
    assert verify_password(PASSWORD, user.password)


def test_users_create_rejects_a_duplicate_and_a_short_password(app: FlowLab) -> None:
    args = ["users:create", "--email", "dup@example.com", "--password", PASSWORD]

    assert runner.invoke(app.cli, args).exit_code == 0
    assert runner.invoke(app.cli, args).exit_code == 1
    assert runner.invoke(app.cli, ["users:create", "--email", "x@example.com", "--password", "short"]).exit_code == 1


def test_api_keys_create_prints_the_token_once_and_stores_its_hash(app: FlowLab) -> None:
    runner.invoke(app.cli, ["users:create", "--email", "key@example.com", "--password", PASSWORD])

    result = runner.invoke(app.cli, ["api-keys:create", "--email", "key@example.com", "--name", "cli"])

    assert result.exit_code == 0, result.output

    token = result.output.strip().splitlines()[-1]
    assert token.startswith("flk_")

    with app.lifespan():
        db: DB = get_db()
        stored = db.select_models(ApiKey).where_equals("name", "cli").fetch_model()

    assert stored is not None
    assert stored.token_hash == hash_api_key(token)


def test_api_keys_create_for_an_unknown_user_fails(app: FlowLab) -> None:
    result = runner.invoke(app.cli, ["api-keys:create", "--email", "nobody@example.com", "--name", "cli"])

    assert result.exit_code == 1
