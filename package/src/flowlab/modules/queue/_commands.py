import json
import logging
from datetime import UTC, datetime
from typing import Annotated

import typer

from flowlab._queue import get_queue
from flowlab._routing import CommandRouter
from flowlab.modules.queue._worker import Worker

commands = CommandRouter()


def _queues(value: str | None) -> list[str]:
    return [name.strip() for name in (value or "").split(",") if name.strip()]


@commands.command("queue:work")
def work(
    queue: Annotated[
        str | None, typer.Option(help="Queues to work, in priority order: high,default. Defaults to QUEUE_NAME.")
    ] = None,
    once: Annotated[bool, typer.Option(help="Process a single job, then stop.")] = False,
    stop_when_empty: Annotated[bool, typer.Option(help="Stop once the queues are empty.")] = False,
    max_jobs: Annotated[int | None, typer.Option(help="Stop after this many jobs.")] = None,
    sleep: Annotated[float, typer.Option(help="Seconds to wait when the queues are empty.")] = 3,
    log_level: Annotated[
        str, typer.Option(help="Level for log lines written by jobs: DEBUG, INFO, WARNING...")
    ] = "INFO",
) -> None:
    """Run queued jobs until stopped (Ctrl+C lets the current job finish)."""
    logging.basicConfig(level=log_level.upper(), format="%(asctime)s %(levelname)-5s %(name)s: %(message)s")
    worker = Worker(
        get_queue(),
        _queues(queue),
        sleep=sleep,
        max_jobs=1 if once else max_jobs,
        stop_when_empty=stop_when_empty or once,
        log=typer.echo,
    )
    typer.echo(f"Working {', '.join(worker.queues)}")
    worker.run()


@commands.command("queue:failed")
def failed() -> None:
    """List failed jobs, the most recent first."""
    jobs = get_queue().failed()

    if not jobs:
        typer.echo("No failed jobs.")
        return

    for job in jobs:
        name = json.loads(job.payload).get("job", "?")
        reason = job.exception.strip().splitlines()[-1] if job.exception.strip() else ""
        typer.echo(
            f"{job.id}  {datetime.fromtimestamp(job.failed_at, UTC).astimezone():%Y-%m-%d %H:%M:%S}  {job.queue}  {name}  {reason}"
        )


@commands.command("queue:retry")
def retry(ids: Annotated[list[str], typer.Argument(help="Failed job ids, or 'all'.")]) -> None:
    """Put failed jobs back on their queue."""
    queue = get_queue()
    targets = [job.id for job in queue.failed()] if ids == ["all"] else ids
    missing = [id for id in targets if not queue.retry(id)]

    typer.echo(f"Retrying {len(targets) - len(missing)} job(s).")

    if missing:
        typer.echo(f"No failed job with id {', '.join(missing)}.", err=True)
        raise typer.Exit(1)


@commands.command("queue:forget")
def forget(id: Annotated[str, typer.Argument(help="A failed job id.")]) -> None:
    """Delete a failed job."""
    if not get_queue().forget(id):
        typer.echo(f"No failed job with id {id}.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Deleted failed job {id}.")


@commands.command("queue:flush")
def flush() -> None:
    """Delete every failed job."""
    typer.echo(f"Deleted {get_queue().flush()} failed job(s).")


@commands.command("queue:clear")
def clear(
    queue: Annotated[str | None, typer.Option(help="The queue to clear. Defaults to QUEUE_NAME.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Don't ask for confirmation.")] = False,
) -> None:
    """Delete every job waiting on a queue."""
    target = get_queue()
    name = queue or target.default

    if not force:
        typer.confirm(f"Delete every job on the {name} queue?", abort=True)

    typer.echo(f"Deleted {target.clear(name)} job(s) from {name}.")
