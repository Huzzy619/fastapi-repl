"""The asyncio runtime shared by the whole shell session.

Async database drivers (asyncpg, aiosqlite...) bind their connections to the
event loop that created them. If every ``await`` in the shell ran on a fresh
loop, the second query would fail with "attached to a different loop". So a
single :class:`Runtime` owns one loop for the whole session, and every
interface runs coroutines through it.

Libraries such as Tortoise ORM 1.x keep state in context variables. Each
coroutine runs in a task with a copy of the current context, and after it
finishes any variables it set are copied back, so ``await Tortoise.init()`` in
one cell is still visible in the next.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import warnings
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import suppress
from typing import Any, TypeVar

from fastapi_repl.errors import LifespanError

T = TypeVar("T")


async def _await(awaitable: Awaitable[T]) -> T:
    return await awaitable


class Runtime:
    """Owns the event loop used by the shell session."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.closed = False
        self.error_hooks: list[Callable[[BaseException], None]] = []
        """Called with each exception raised by code run on the loop (see :meth:`report_error`)."""
        self._last_error: BaseException | None = None

    def run(self, awaitable: Awaitable[T]) -> T:
        """Run an awaitable to completion on the session loop and return its result.

        Context variables set by the awaitable are propagated back to the caller.
        Ctrl+C cancels the awaitable and re-raises ``KeyboardInterrupt``.

        Raises:
            RuntimeError: If called while the loop is already running (for
                example from inside ptpython, where you can ``await`` directly).
        """
        if self.loop.is_running():
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise RuntimeError(
                "The event loop is already running here; use 'await' instead of await_()."
            )
        coro: Coroutine[Any, Any, T] = (
            awaitable if inspect.iscoroutine(awaitable) else _await(awaitable)
        )
        context = contextvars.copy_context()
        task = self.loop.create_task(coro, context=context)
        try:
            return self.loop.run_until_complete(task)
        except KeyboardInterrupt:
            task.cancel()
            with suppress(BaseException):
                self.loop.run_until_complete(task)
            raise
        except Exception as exc:
            self.report_error(exc)
            raise
        finally:
            self.adopt_context(context)

    def report_error(self, error: BaseException) -> None:
        """Tell the error hooks that user code raised ``error``.

        Called automatically for awaitables run through :meth:`run`.
        Interfaces also call it for errors in synchronous code. Each exception
        is reported once, and a failing hook never hides the original error.
        """
        if error is self._last_error or isinstance(error, (KeyboardInterrupt, SystemExit)):
            return
        self._last_error = error
        for hook in list(self.error_hooks):
            if self.loop.is_running():
                break
            with suppress(Exception):
                hook(error)

    def resolve(self, value: T | Awaitable[T]) -> T:
        """Return ``value``, awaiting it first if it is awaitable."""
        if inspect.isawaitable(value):
            return self.run(value)
        return value  # type: ignore[return-value]

    def await_(self, awaitable: Awaitable[T]) -> T:
        """Run an awaitable and return its result. Exposed in the shell as ``await_``.

        Useful in interfaces without top-level ``await`` support (bpython) and
        in synchronous helper code.
        """
        return self.run(awaitable)

    @staticmethod
    def adopt_context(context: contextvars.Context) -> None:
        """Copy variables set in ``context`` into the current context."""
        for var, value in context.items():
            try:
                if var.get() is value:
                    continue
            except LookupError:
                pass
            var.set(value)

    def close(self) -> None:
        """Cancel leftover tasks and close the loop."""
        if self.closed:
            return
        self.closed = True
        loop = self.loop
        try:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


class LifespanManager:
    """Drives an ASGI application's lifespan protocol.

    This speaks raw ASGI rather than calling framework internals, so it works
    with FastAPI, Starlette, Litestar, Quart and any other ASGI 3 app.

    The app runs in a background task on the session loop. After
    :meth:`startup`, the task sits waiting for the shutdown message, which
    :meth:`shutdown` sends when the shell exits.
    """

    def __init__(self, app: Any, *, timeout: float | None = 60.0) -> None:
        self.app = app
        self.timeout = timeout
        self.state: dict[str, Any] = {}
        self.supported = True
        self.started = False
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._startup_done: asyncio.Event | None = None
        self._shutdown_done: asyncio.Event | None = None
        self._task: asyncio.Task[None] | None = None
        self._context: contextvars.Context | None = None
        self._error: str | None = None

    async def _receive(self) -> dict[str, Any]:
        assert self._queue is not None
        return await self._queue.get()

    async def _send(self, message: dict[str, Any]) -> None:
        assert self._startup_done is not None
        assert self._shutdown_done is not None
        kind = message.get("type")
        if kind == "lifespan.startup.complete":
            self._startup_done.set()
        elif kind == "lifespan.startup.failed":
            self._error = message.get("message") or "lifespan startup failed"
            self._startup_done.set()
        elif kind == "lifespan.shutdown.complete":
            self._shutdown_done.set()
        elif kind == "lifespan.shutdown.failed":
            self._error = message.get("message") or "lifespan shutdown failed"
            self._shutdown_done.set()

    async def _run_app(self) -> None:
        scope = {
            "type": "lifespan",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "state": self.state,
        }
        await self.app(scope, self._receive, self._send)

    async def _wait(self, event: asyncio.Event) -> None:
        assert self._task is not None
        waiter = asyncio.ensure_future(event.wait())
        try:
            await asyncio.wait(
                {self._task, waiter},
                timeout=self.timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            waiter.cancel()
            with suppress(asyncio.CancelledError):
                await waiter

    async def startup(self) -> dict[str, Any]:
        """Send ``lifespan.startup`` and wait for the app to finish starting.

        Returns:
            The lifespan ``state`` dict (what ``request.state`` would see).

        Raises:
            LifespanError: If the app reports a startup failure or times out.
        """
        self._queue = asyncio.Queue()
        self._startup_done = asyncio.Event()
        self._shutdown_done = asyncio.Event()
        self._context = contextvars.copy_context()
        self._task = asyncio.get_running_loop().create_task(self._run_app(), context=self._context)
        await self._queue.put({"type": "lifespan.startup"})
        await self._wait(self._startup_done)

        if self._error is not None:
            await self._reap()
            raise LifespanError(f"Application startup failed: {self._error}")
        if not self._startup_done.is_set():
            if self._task.done():
                exc = self._task.exception()
                self.supported = False
                warnings.warn(
                    f"The app does not support the ASGI lifespan protocol ({exc!r}); "
                    "continuing without startup/shutdown.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                return self.state
            self._task.cancel()
            await self._reap()
            raise LifespanError(f"Application startup timed out after {self.timeout} seconds.")

        self.started = True
        Runtime.adopt_context(self._context)
        return self.state

    async def shutdown(self) -> None:
        """Send ``lifespan.shutdown`` and wait for the app to finish.

        Raises:
            LifespanError: If the app reports a shutdown failure.
        """
        if not self.started or self._task is None or self._queue is None:
            return
        assert self._shutdown_done is not None
        self.started = False
        await self._queue.put({"type": "lifespan.shutdown"})
        await self._wait(self._shutdown_done)
        if not self._task.done():
            self._task.cancel()
        await self._reap()
        if self._error is not None:
            raise LifespanError(f"Application shutdown failed: {self._error}")

    async def _reap(self) -> None:
        if self._task is None:
            return
        with suppress(BaseException):
            await self._task
