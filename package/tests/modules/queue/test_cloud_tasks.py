import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from flowlab import FlowLab, QueueSettings
from flowlab._settings import DatabaseSettings
from flowlab.modules.db import DB
from flowlab.modules.queue import Queue, job
from flowlab.modules.queue._push import GoogleTokenVerifier, pushed_job

tasks_v2 = pytest.importorskip("google.cloud.tasks_v2")

URL = "https://worker-abc.a.run.app"
SERVICE_ACCOUNT = "tasks@project.iam.gserviceaccount.com"
PATH = "projects/project/locations/europe-west1/queues"

calls: list[Any] = []


@job
def record(value: Any) -> None:
    calls.append(value)


@job(tries=3, backoff=[30, 60])
def broken() -> None:
    calls.append("broken")
    raise ValueError("always broken")


class FakeTasksClient:
    def __init__(self) -> None:
        self.tasks: dict[str, list[dict[str, Any]]] = {}
        self.transport = self
        self.closed = False

    def create_task(self, parent: str, task: dict[str, Any]) -> None:
        tasks_v2.CreateTaskRequest(parent=parent, task=task)  # the real client must accept it
        self.tasks.setdefault(parent, []).append(task)

    def list_tasks(self, parent: str) -> list[dict[str, Any]]:
        return list(self.tasks.get(parent, []))

    def purge_queue(self, name: str) -> None:
        self.tasks.pop(name, None)

    def close(self) -> None:
        self.closed = True

    def all(self) -> list[dict[str, Any]]:
        return [task for tasks in self.tasks.values() for task in tasks]


@pytest.fixture(autouse=True)
def _reset_calls() -> Iterator[None]:
    calls.clear()
    yield
    calls.clear()


@pytest.fixture()
def client_stub(monkeypatch: pytest.MonkeyPatch) -> FakeTasksClient:
    stub = FakeTasksClient()
    monkeypatch.setattr(tasks_v2, "CloudTasksClient", lambda: stub)
    monkeypatch.setattr(GoogleTokenVerifier, "__call__", lambda self, token: token == "good")
    return stub


def settings(**overrides: Any) -> QueueSettings:
    return QueueSettings(
        **{
            "queue_driver": "cloudtasks",
            "queue_gcp_project": "project",
            "queue_gcp_location": "europe-west1",
            "queue_target_url": URL,
            "queue_service_account": SERVICE_ACCOUNT,
            **overrides,
        }
    )


@pytest.fixture()
def app(tmp_path: Path, client_stub: FakeTasksClient) -> FlowLab:
    app = FlowLab(
        database_settings=DatabaseSettings(db_driver="sqlite", db_name=str(tmp_path / "app.sqlite")),
        queue_settings=settings(),
        project_dir=tmp_path,
    )
    runner = CliRunner()
    assert runner.invoke(app.cli, ["queue:install"]).exit_code == 0
    assert runner.invoke(app.cli, ["migrations:up"]).exit_code == 0
    return app


@pytest.fixture()
def http(app: FlowLab) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def deliver(http: TestClient, task: dict[str, Any], token: str = "good", retries: int = 0) -> int:
    request = task["http_request"]
    headers = {
        **request["headers"],
        "Authorization": f"Bearer {token}",
        "X-CloudTasks-QueueName": "default",
        "X-CloudTasks-TaskName": "task-1",
        "X-CloudTasks-TaskRetryCount": str(retries),
    }
    return http.post(request["url"].removeprefix(URL), content=request["body"], headers=headers).status_code


def test_dispatch_creates_a_task_that_calls_the_app_back(
    app: FlowLab, http: TestClient, client_stub: FakeTasksClient
) -> None:
    record.dispatch(1)

    [task] = client_stub.tasks[f"{PATH}/default"]
    request = task["http_request"]
    assert request["url"] == f"{URL}/_flowlab/queue"
    assert request["oidc_token"] == {"service_account_email": SERVICE_ACCOUNT, "audience": URL}
    assert request["headers"]["X-Flowlab-Attempts"] == "0"
    assert task["dispatch_deadline"] == timedelta(seconds=90)
    assert "schedule_time" not in task
    assert calls == []

    assert deliver(http, task) == 204
    assert calls == [1]
    assert app.queue.size() == 1  # the fake never removes delivered tasks; Cloud Tasks does


def test_later_schedules_the_task(app: FlowLab, http: TestClient, client_stub: FakeTasksClient) -> None:
    record.later(60, 1)

    [task] = client_stub.all()
    assert abs((task["schedule_time"] - datetime.now(UTC)).total_seconds() - 60) < 5


def test_a_failing_job_is_scheduled_again_after_its_backoff(
    app: FlowLab, http: TestClient, client_stub: FakeTasksClient
) -> None:
    broken.dispatch()
    first = client_stub.all()[0]

    assert deliver(http, first) == 204
    retry = client_stub.all()[1]
    assert retry["http_request"]["headers"]["X-Flowlab-Attempts"] == "1"
    assert abs((retry["schedule_time"] - datetime.now(UTC)).total_seconds() - 30) < 5

    assert deliver(http, retry) == 204
    last = client_stub.all()[2]
    assert last["http_request"]["headers"]["X-Flowlab-Attempts"] == "2"

    assert deliver(http, last) == 204
    assert len(client_stub.all()) == 3
    assert calls == ["broken"] * 3

    [failed] = app.queue.failed()
    assert "ValueError: always broken" in failed.exception


def test_failed_jobs_can_be_retried(app: FlowLab, http: TestClient, client_stub: FakeTasksClient) -> None:
    broken.dispatch()
    deliver(http, client_stub.all()[0], retries=5)  # Cloud Tasks retried crashed requests: attempts are used up

    [failed] = app.queue.failed()
    assert CliRunner().invoke(app.cli, ["queue:retry", failed.id]).exit_code == 0
    assert app.queue.failed() == []
    assert client_stub.all()[-1]["http_request"]["headers"]["X-Flowlab-Attempts"] == "0"


def test_requests_without_a_valid_token_are_refused(
    app: FlowLab, http: TestClient, client_stub: FakeTasksClient
) -> None:
    record.dispatch(1)
    [task] = client_stub.all()

    assert deliver(http, task, token="forged") == 401
    assert http.post("/_flowlab/queue", content=task["http_request"]["body"]).status_code == 401
    assert calls == []


def test_clear_purges_the_queue(app: FlowLab, client_stub: FakeTasksClient) -> None:
    with app.lifespan():
        record.dispatch(1)
        record.dispatch(2)

        assert app.queue.clear() == 2
        assert app.queue.size() == 0


def test_there_is_no_worker_to_run(app: FlowLab) -> None:
    result = CliRunner().invoke(app.cli, ["queue:work"])

    assert result.exit_code == 1
    assert "no worker" in result.output


def test_the_failed_jobs_table_is_required(tmp_path: Path, client_stub: FakeTasksClient) -> None:
    from flowlab import SchemaMismatch

    app = FlowLab(
        database_settings=DatabaseSettings(db_driver="sqlite", db_name=str(tmp_path / "app.sqlite")),
        queue_settings=settings(),
        project_dir=tmp_path,
    )

    with pytest.raises(SchemaMismatch, match="failed_jobs"), TestClient(app):
        pass


def test_settings_are_required() -> None:
    with pytest.raises(ValueError, match="QUEUE_GCP_PROJECT, QUEUE_SERVICE_ACCOUNT"):
        settings(queue_gcp_project="", queue_service_account=None)


def test_the_deadline_follows_retry_after_within_cloud_tasks_limits(client_stub: FakeTasksClient) -> None:
    db = DB.connect_sqlite(":memory:")

    for retry_after, deadline in ((5, 15), (600, 600), (7200, 1800)):
        options = settings(queue_retry_after=retry_after).queue_options()
        Queue.connect_cloud_tasks(db, client=client_stub, **options).push("x:y")
        assert client_stub.all()[-1]["dispatch_deadline"] == timedelta(seconds=deadline)


def test_attempts_add_up_earlier_tasks_and_cloud_tasks_retries() -> None:
    headers = {"X-Flowlab-Attempts": "2", "X-CloudTasks-TaskRetryCount": "1", "X-CloudTasks-QueueName": "emails"}
    job = pushed_job('{"id": "abc", "job": "x:y", "args": [], "kwargs": {}}', headers, "default")

    assert (job.id, job.queue, job.attempts) == ("abc", "emails", 4)
    assert pushed_job("not json", {"X-CloudTasks-TaskName": "t"}, "default").id == "t"


def test_the_verifier_checks_signature_audience_and_service_account() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from google.auth import crypt
    from google.auth import jwt as google_jwt

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    signer = crypt.RSASigner.from_string(private, key_id="k1")

    verifier = GoogleTokenVerifier(URL, SERVICE_ACCOUNT)
    verifier._certs, verifier._fetched_at = {"k1": public.decode()}, time.monotonic()

    def token(**claims: Any) -> str:
        now = int(time.time())
        base = {"iss": "https://accounts.google.com", "aud": URL, "email": SERVICE_ACCOUNT, "email_verified": True}
        return google_jwt.encode(signer, {**base, "iat": now, "exp": now + 300, **claims}).decode()

    assert verifier(token())
    assert not verifier(token(aud="https://elsewhere.example"))
    assert not verifier(token(email="someone@else.iam.gserviceaccount.com"))
    assert not verifier(token(iss="https://evil.example"))
    assert not verifier(token(exp=int(time.time()) - 60))
    assert not verifier("not a token")


def test_the_verifier_fetches_certificates_once_and_not_for_every_unknown_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from google.auth.transport import requests as transport

    fetches: list[str] = []

    class Response:
        status = 200
        data = json.dumps({"k1": "cert"}).encode()

    monkeypatch.setattr(transport, "Request", lambda: lambda url, method: fetches.append(url) or Response())
    verifier = GoogleTokenVerifier(URL, SERVICE_ACCOUNT)

    assert verifier._certificates(refresh=False) == {"k1": "cert"}
    assert verifier._certificates(refresh=True) == {"k1": "cert"}
    assert len(fetches) == 1
