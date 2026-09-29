from pathlib import Path

from flowlab._module import Module
from flowlab.modules.queue._job import Job, JobNotFound, job, resolve
from flowlab.modules.queue._queue import Queue
from flowlab.modules.queue._schema import check_schema
from flowlab.modules.queue._worker import Worker
from flowlab.modules.queue.adapters import FailedJob, ReservedJob

__all__ = [
    "MIGRATIONS_DIR",
    "FailedJob",
    "Job",
    "JobNotFound",
    "Queue",
    "ReservedJob",
    "Worker",
    "job",
    "module",
    "resolve",
]

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def module() -> Module:
    from flowlab.modules.queue._commands import commands

    return Module(name="queue", routers=[commands], migrations=MIGRATIONS_DIR, check=check_schema)
