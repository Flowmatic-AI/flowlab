from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from flowlab import FlowLab, QueueSettings, SchemaMismatch, get_db
from flowlab._settings import DatabaseSettings
from flowlab.modules.queue import Job, JobNotFound, Worker, job, resolve

calls: list[Any] = []


@job
def record(value: Any, *, label: str = "") -> None:
    calls.append((value, label))


@job(queue="emails")
def send_email(to: str) -> None:
    calls.append(("email", to))


@job(tries=3, backoff=[0, 0])
def flaky(fail_times: int) -> None:
    calls.append("flaky")

    if calls.count("flaky") <= fail_times:
        raise RuntimeError(f"attempt {calls.count('flaky')} failed")


@job
def broken() -> None:
    raise ValueError("always broken")


@job
async def async_record(value: int) -> None:
    calls.append(("async", value))


@job
def uses_the_database() -> None:
    calls.append(get_db().select("jobs").columns(["uuid"]).execute().fetch_dicts() != [])


def not_a_job() -> None:
    pass


@pytest.fixture(autouse=True)
def _reset_calls() -> Iterator[None]:
    calls.clear()
    yield
    calls.clear()


def make_app(tmp_path: Path, driver: str = "database") -> FlowLab:
    return FlowLab(
        database_settings=DatabaseSettings(db_driver="sqlite", db_name=str(tmp_path / "app.sqlite")),
        queue_settings=QueueSettings(queue_driver=driver),
        project_dir=tmp_path,
    )


@pytest.fixture()
def app(tmp_path: Path) -> Iterator[FlowLab]:
    app = make_app(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app.cli, ["queue:install"]).exit_code == 0
    assert runner.invoke(app.cli, ["migrations:up"]).exit_code == 0

    with app.lifespan():
        yield app


def work(app: FlowLab, *queues: str) -> int:
    return Worker(app.queue, queues, stop_when_empty=True, log=lambda line: None).run()


def test_dispatch_queues_the_job_and_a_worker_runs_it(app: FlowLab) -> None:
    id = record.dispatch(1, label="one")

    assert calls == []
    assert app.queue.size() == 1
    assert work(app) == 1
    assert calls == [(1, "one")]
    assert app.queue.size() == 0
    assert len(id) == 32


def test_a_job_goes_to_its_own_queue(app: FlowLab) -> None:
    send_email.dispatch("ada@example.com")

    assert app.queue.size("emails") == 1
    assert work(app) == 0
    assert work(app, "emails") == 1
    assert calls == [("email", "ada@example.com")]


def test_later_waits(app: FlowLab) -> None:
    record.later(60, 1)

    assert work(app) == 0
    assert app.queue.size() == 1


def test_a_failing_job_is_retried_until_it_succeeds(app: FlowLab) -> None:
    flaky.dispatch(2)

    assert work(app) == 3
    assert calls == ["flaky"] * 3
    assert app.queue.failed() == []


def test_a_job_that_keeps_failing_ends_up_failed(app: FlowLab) -> None:
    flaky.dispatch(5)
    broken.dispatch()

    work(app)

    failed = app.queue.failed()
    assert calls == ["flaky"] * 3
    assert len(failed) == 2
    assert "ValueError: always broken" in failed[1].exception or "ValueError: always broken" in failed[0].exception
    assert any("RuntimeError: attempt 3 failed" in job.exception for job in failed)


def test_async_jobs_run(app: FlowLab) -> None:
    async_record.dispatch(7)
    work(app)

    assert calls == [("async", 7)]


def test_jobs_run_inside_the_app_lifespan(app: FlowLab) -> None:
    uses_the_database.dispatch()
    work(app)

    assert calls == [True]


def test_a_payload_naming_something_that_is_not_a_job_fails_without_running_it(app: FlowLab) -> None:
    app.queue.push(f"{__name__}:not_a_job")
    app.queue.push("os:system", ["echo hacked"])
    app.queue.push("no.such.module:job")

    work(app)

    assert [job.exception.strip().splitlines()[-1] for job in app.queue.failed()] == [
        "flowlab.modules.queue._job.JobNotFound: No job 'no.such.module:job': it could not be imported",
        "flowlab.modules.queue._job.JobNotFound: 'os:system' is not a @job",
        f"flowlab.modules.queue._job.JobNotFound: '{__name__}:not_a_job' is not a @job",
    ]


def test_dispatch_checks_the_arguments_up_front(app: FlowLab) -> None:
    with pytest.raises(TypeError):
        record.dispatch()  # type: ignore[call-arg]

    with pytest.raises(TypeError, match="must be JSON serializable"):
        record.dispatch(object())

    assert app.queue.size() == 0


def test_calling_a_job_runs_it_now(app: FlowLab) -> None:
    record(3)

    assert calls == [(3, "")]
    assert app.queue.size() == 0


def test_sync_driver_runs_jobs_on_dispatch(tmp_path: Path) -> None:
    app = make_app(tmp_path, "sync")

    with app.lifespan():
        record.dispatch(1)

        assert calls == [(1, "")]

        with pytest.raises(ValueError, match="always broken"):
            broken.dispatch()


def test_resolve_finds_jobs_by_name() -> None:
    assert resolve(record.name) is record
    assert record.name == f"{__name__}:record"
    assert isinstance(record, Job)

    with pytest.raises(JobNotFound):
        resolve(f"{__name__}:not_a_job")


def test_jobs_must_be_module_level() -> None:
    with pytest.raises(TypeError, match="module level"):

        @job
        def nested() -> None:
            pass


def test_backoff_per_retry() -> None:
    definition = Job(not_a_job, tries=4, backoff=[10, 60])

    assert [definition.retry_delay(attempts) for attempts in (1, 2, 3)] == [10, 60, 60]
    assert Job(not_a_job, backoff=5).retry_delay(3) == 5


def test_commands(app: FlowLab) -> None:
    runner = CliRunner()
    record.dispatch(1)
    broken.dispatch()
    broken.dispatch()

    worked = runner.invoke(app.cli, ["queue:work", "--stop-when-empty"])
    assert worked.exit_code == 0, worked.output
    assert worked.output.count("DONE") == 1
    assert worked.output.count("FAIL") == 2

    failed_ids = [job.id for job in app.queue.failed()]
    listing = runner.invoke(app.cli, ["queue:failed"])
    assert all(id in listing.output for id in failed_ids)
    assert "ValueError: always broken" in listing.output

    assert runner.invoke(app.cli, ["queue:retry", failed_ids[0]]).exit_code == 0
    assert app.queue.size() == 1
    assert runner.invoke(app.cli, ["queue:retry", "nope"]).exit_code == 1

    assert runner.invoke(app.cli, ["queue:forget", failed_ids[1]]).exit_code == 0
    assert app.queue.failed() == []

    once = runner.invoke(app.cli, ["queue:work", "--once"])
    assert once.output.count("FAIL") == 1
    assert "Deleted 1 failed job(s)." in runner.invoke(app.cli, ["queue:flush"]).output

    record.dispatch(2)
    assert "Deleted 1 job(s) from default." in runner.invoke(app.cli, ["queue:clear", "--force"]).output
    assert runner.invoke(app.cli, ["queue:retry", "all"]).output.startswith("Retrying 0 job(s).")


def test_database_driver_refuses_to_start_without_its_tables(tmp_path: Path) -> None:
    with pytest.raises(SchemaMismatch, match="queue:install"), TestClient(make_app(tmp_path)):
        pass


def test_other_drivers_skip_the_table_check(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path, "sync")) as client:
        assert client.get("/health").status_code == 200


def test_the_worker_configures_logging_for_jobs(app: FlowLab, monkeypatch: pytest.MonkeyPatch) -> None:
    configured: list[dict[str, Any]] = []
    monkeypatch.setattr("logging.basicConfig", lambda **options: configured.append(options))

    CliRunner().invoke(app.cli, ["queue:work", "--stop-when-empty", "--log-level", "debug"])

    assert configured and configured[0]["level"] == "DEBUG"
