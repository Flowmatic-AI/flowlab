from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Generic, Self, TypeVar

from flowlab.modules.db import AdapterError, ConnectionLimitError

T = TypeVar("T")

_SHARED_KEY = "shared"


class _ThreadExitHook:
    """Runs ``callback`` at the moment the thread that armed it exits.

    The hook is parked in a :class:`threading.local`, so CPython drops the last
    reference to it while tearing that thread's state down, and ``__del__`` runs
    *in the dying thread* while it can still do IO. That is what lets a store
    evict -- and an adapter close -- a finished thread's value immediately,
    rather than leaving it open until some later caller happens to notice.

    ``key`` is captured up front on purpose: by the time ``__del__`` runs the
    thread is already out of ``threading._active``, so
    :func:`threading.current_thread` would hand back a fresh dummy object."""

    def __init__(
        self,
        key: threading.Thread,
        callback: Callable[[threading.Thread], None],
    ) -> None:
        self._key = key
        self._callback = callback
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def __del__(self) -> None:
        if self._cancelled:
            return

        # This runs during thread teardown, where an escaping exception is
        # unraisable noise on stderr that no caller is in a position to handle.
        with contextlib.suppress(Exception):
            self._callback(self._key)


class _ThreadExitHookSlot(threading.local):
    """Holds one store's exit hook for the calling thread.

    :class:`threading.local` re-runs ``__init__`` for every thread that touches
    the instance, so ``hook`` is always bound."""

    def __init__(self) -> None:
        super().__init__()
        self.hook: _ThreadExitHook | None = None


class _SlotReservation:
    """One permit borrowed against a store's ``max_values`` limit.

    A permit is taken *before* the value it will hold is created -- for an
    adapter, before the driver connection is opened -- because the whole point
    is to not open past the limit. It is held until either :meth:`transfer`
    hands it to a stored value, which then owns it until that value is evicted,
    or the ``with`` block ends without one (an open that raised), which hands it
    straight back to the next thread in line."""

    def __init__(self, slot: _SlotReservationSlot, semaphore: threading.Semaphore | None) -> None:
        self._slot = slot
        self._semaphore = semaphore
        self._held = semaphore is not None

    def transfer(self) -> None:
        self._held = False

    def release(self) -> None:
        if not self._held:
            return

        self._held = False
        if self._semaphore is not None:
            self._semaphore.release()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._slot.reservation = None
        self.release()


class _SlotReservationSlot(threading.local):
    """Holds the calling thread's in-flight reservation, so :meth:`ThreadLocalStore.set`
    can find the permit that was taken for the value being bound."""

    def __init__(self) -> None:
        super().__init__()
        self.reservation: _SlotReservation | None = None


class ThreadLocalStore(Generic[T]):
    def __init__(
        self,
        shared_across_threads: bool = False,
        on_thread_exit: Callable[[T], None] | None = None,
        max_values: int | None = None,
        acquire_timeout: float | None = None,
    ) -> None:
        if max_values is not None and max_values < 1:
            raise AdapterError("max_values must be at least 1")

        self._shared_across_threads = shared_across_threads
        self._on_thread_exit = on_thread_exit
        self._max_values = max_values
        self._acquire_timeout = acquire_timeout
        self._semaphore = threading.Semaphore(max_values) if max_values is not None else None
        self._lock = threading.RLock()
        self._values: dict[threading.Thread | str, T] = {}
        self._hooks = _ThreadExitHookSlot()
        self._reservations = _SlotReservationSlot()

    @property
    def shared_across_threads(self) -> bool:
        return self._shared_across_threads

    @property
    def max_values(self) -> int | None:
        return self._max_values

    def reserve(self) -> _SlotReservation:
        """Claim a slot, blocking until one is free.

        Waiters are served in arrival order: :class:`threading.Semaphore` parks
        them on a :class:`threading.Condition`, whose ``notify()`` wakes the one
        that has waited longest. An unlimited store hands back a reservation
        that owns no permit, so the call sites need no branch.

        Raises :class:`ConnectionLimitError` when ``acquire_timeout`` elapses
        first."""
        if self._semaphore is None:
            reservation = _SlotReservation(self._reservations, None)
        else:
            if self._acquire_timeout is None:
                self._semaphore.acquire()
            elif not self._semaphore.acquire(timeout=self._acquire_timeout):
                raise ConnectionLimitError(
                    f"no connection slot came free within {self._acquire_timeout}s "
                    f"(limit is {self._max_values} concurrent connections)"
                )

            reservation = _SlotReservation(self._reservations, self._semaphore)

        self._reservations.reservation = reservation
        return reservation

    def _release_slots(self, count: int) -> None:
        """Hand ``count`` slots back.

        Every entry is popped by exactly one path, so each releases exactly
        once. Callers that dispose of the value themselves -- :meth:`discard`,
        :meth:`take_all`, :meth:`take_orphaned` -- release as they pop, which
        can briefly overlap a new connection with one still closing; only
        :meth:`_release` can order the two, and it does."""
        if self._semaphore is None or count < 1:
            return

        self._semaphore.release(count)

    def _key(self) -> threading.Thread | str:
        if self._shared_across_threads:
            return _SHARED_KEY

        return threading.current_thread()

    def _arm_hook(self, key: threading.Thread) -> None:
        if self._hooks.hook is not None:
            return

        self._hooks.hook = _ThreadExitHook(key, self._release)

    def _disarm_hook(self) -> None:
        hook = self._hooks.hook
        if hook is None:
            return

        hook.cancel()
        self._hooks.hook = None

    def _release(self, key: threading.Thread) -> None:
        """Evict a dead thread's value and hand it to ``on_thread_exit``.

        The pop happens under the lock, so this races safely against
        :meth:`take_all` and :meth:`take_orphaned` -- whoever pops the value is
        the only one that disposes of it, and the only one that hands its slot
        back."""
        with self._lock:
            value = self._values.pop(key, None)

        if value is None:
            return

        try:
            if self._on_thread_exit is not None:
                self._on_thread_exit(value)
        finally:
            # Freed only once the value is really gone. Handing the slot on
            # first would let whoever takes it open a new connection while this
            # one is still closing, briefly putting the driver over the limit --
            # and this is the path every slot normally comes back through.
            self._release_slots(1)

    def current(self) -> T | None:
        with self._lock:
            return self._values.get(self._key())

    def require(self) -> T:
        with self._lock:
            value = self._values.get(self._key())

        if value is None:
            raise AdapterError("no connection is bound to the current thread")

        return value

    def set(self, value: T) -> None:
        key = self._key()
        reservation = self._reservations.reservation

        with self._lock:
            occupied = key in self._values
            self._values[key] = value

            if reservation is not None:
                # An occupied key already paid for its slot, so a second permit
                # for it would leave the store one short forever. Otherwise the
                # permit becomes this entry's, and comes back when it is evicted.
                if occupied:
                    reservation.release()
                else:
                    reservation.transfer()

        # A shared value outlives every individual thread, so it must not be
        # torn down when one of them exits.
        if isinstance(key, threading.Thread):
            self._arm_hook(key)

    def discard(self) -> T | None:
        key = self._key()
        with self._lock:
            value = self._values.pop(key, None)
            if value is not None:
                self._release_slots(1)

        if isinstance(key, threading.Thread):
            self._disarm_hook()

        return value

    def values(self) -> list[T]:
        with self._lock:
            return list(self._values.values())

    def take_all(self) -> list[T]:
        with self._lock:
            values = list(self._values.values())
            self._values.clear()
            self._release_slots(len(values))

        return values

    def take_orphaned(self) -> list[T]:
        """Sweep values whose thread has finished.

        A backstop only: :class:`_ThreadExitHook` normally evicts these at the
        instant the thread exits. This still catches the cases the hook cannot
        reach -- a thread killed without running its teardown, or a value bound
        before the hook was armed."""
        with self._lock:
            orphaned = [key for key in self._values if isinstance(key, threading.Thread) and not key.is_alive()]
            values = [self._values.pop(key) for key in orphaned]
            self._release_slots(len(values))
            return values

    def count(self) -> int:
        with self._lock:
            return len(self._values)
