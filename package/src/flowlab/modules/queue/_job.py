from __future__ import annotations

import functools
import importlib
import inspect
import json
from collections.abc import Callable, Sequence
from typing import Any, overload

import anyio


class JobNotFound(LookupError):
    pass


class Job[**P]:
    """A function a worker can run later. Create one with ``@job``."""

    def __init__(
        self,
        function: Callable[P, Any],
        *,
        queue: str | None = None,
        tries: int = 1,
        backoff: float | Sequence[float] = 0,
    ) -> None:
        if "<locals>" in function.__qualname__:
            raise TypeError(f"@job {function.__qualname__} must be defined at module level, so a worker can import it")

        if tries < 1:
            raise ValueError("tries must be at least 1")

        functools.update_wrapper(self, function)
        self.function = function
        self.name = f"{function.__module__}:{function.__qualname__}"
        self.queue = queue
        self.tries = tries
        self.backoff = backoff
        self._signature = inspect.signature(function)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Any:
        """Run the job now, in this process."""
        if inspect.iscoroutinefunction(self.function):
            return anyio.run(functools.partial(self.function, *args, **kwargs))

        return self.function(*args, **kwargs)

    def dispatch(self, *args: P.args, **kwargs: P.kwargs) -> str:
        """Queue the job and return its id."""
        return self._push(0, args, kwargs)

    def later(self, delay: float, *args: P.args, **kwargs: P.kwargs) -> str:
        """Queue the job to run in ``delay`` seconds and return its id."""
        return self._push(delay, args, kwargs)

    def retry_delay(self, attempts: int) -> float:
        """Seconds to wait before the next try, after ``attempts`` tries failed."""
        if isinstance(self.backoff, int | float):
            return float(self.backoff)

        if not self.backoff:
            return 0.0

        return float(self.backoff[min(attempts, len(self.backoff)) - 1])

    def _push(self, delay: float, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        from flowlab._queue import get_queue

        self._signature.bind(*args, **kwargs)

        return get_queue().push(self.name, args, kwargs, queue=self.queue, delay=delay)

    def __repr__(self) -> str:
        return f"<Job {self.name}>"


@overload
def job[**P](function: Callable[P, Any], /) -> Job[P]: ...


@overload
def job[**P](
    *, queue: str | None = None, tries: int = 1, backoff: float | Sequence[float] = 0
) -> Callable[[Callable[P, Any]], Job[P]]: ...


def job[**P](
    function: Callable[P, Any] | None = None,
    /,
    *,
    queue: str | None = None,
    tries: int = 1,
    backoff: float | Sequence[float] = 0,
) -> Job[P] | Callable[[Callable[P, Any]], Job[P]]:
    """Turn a function into a queued job: ``@job`` or ``@job(queue="emails", tries=3, backoff=[10, 60])``.

    ``tries`` is how many times a worker runs it before it counts as failed; ``backoff`` is the wait in seconds
    between tries, one number or one per retry. Arguments must be JSON serializable.
    """

    def decorate(function: Callable[P, Any]) -> Job[P]:
        return Job(function, queue=queue, tries=tries, backoff=backoff)

    return decorate(function) if function is not None else decorate


def resolve(name: str) -> Job[...]:
    """Find the job at ``"package.module:function"``. Only ``@job`` functions resolve, so a payload can't name an
    arbitrary callable."""
    module_name, _, qualname = name.partition(":")

    try:
        target: Any = importlib.import_module(module_name)

        for attribute in qualname.split("."):
            target = getattr(target, attribute)
    except (ImportError, AttributeError, ValueError):
        raise JobNotFound(f"No job {name!r}: it could not be imported") from None

    if not isinstance(target, Job):
        raise JobNotFound(f"{name!r} is not a @job")

    return target


def decode(payload: str) -> tuple[Job[...], list[Any], dict[str, Any]]:
    data = json.loads(payload)
    return resolve(data["job"]), data["args"], data["kwargs"]


def perform(payload: str) -> Any:
    definition, args, kwargs = decode(payload)
    return definition(*args, **kwargs)
