from __future__ import annotations

import asyncio
import contextvars

import pytest

from fastapi_repl.errors import LifespanError
from fastapi_repl.runtime import LifespanManager, Runtime

VAR: contextvars.ContextVar[str] = contextvars.ContextVar("VAR", default="unset")


@pytest.fixture
def runtime():
    rt = Runtime()
    yield rt
    rt.close()


def test_run_returns_result(runtime: Runtime) -> None:
    async def add(a: int, b: int) -> int:
        await asyncio.sleep(0)
        return a + b

    assert runtime.run(add(1, 2)) == 3


def test_same_loop_for_every_call(runtime: Runtime) -> None:
    async def current() -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    assert runtime.run(current()) is runtime.run(current()) is runtime.loop


def test_accepts_futures_and_other_awaitables(runtime: Runtime) -> None:
    future = runtime.loop.create_future()
    runtime.loop.call_soon(future.set_result, "done")
    assert runtime.run(future) == "done"


def test_resolve_passes_plain_values_through(runtime: Runtime) -> None:
    assert runtime.resolve(5) == 5


def test_context_variables_propagate(runtime: Runtime) -> None:
    token = VAR.set("before")
    try:

        async def setter() -> None:
            VAR.set("from task")

        async def getter() -> str:
            return VAR.get()

        runtime.run(setter())
        assert VAR.get() == "from task"
        assert runtime.run(getter()) == "from task"
    finally:
        VAR.reset(token)


def test_run_inside_running_loop_is_an_error(runtime: Runtime) -> None:
    async def nested() -> None:
        runtime.run(asyncio.sleep(0))

    with pytest.raises(RuntimeError, match="already running"):
        runtime.run(nested())


def test_close_cancels_leftover_tasks() -> None:
    rt = Runtime()
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.sleep(3600)

    task = rt.loop.create_task(forever())
    rt.run(started.wait())
    rt.close()
    assert task.cancelled()
    assert rt.loop.is_closed()
    rt.close()  # idempotent


class LifespanApp:
    """A minimal raw ASGI app."""

    def __init__(self, fail_startup: bool = False, fail_shutdown: bool = False) -> None:
        self.events: list[str] = []
        self.fail_startup = fail_startup
        self.fail_shutdown = fail_shutdown

    async def __call__(self, scope, receive, send) -> None:
        assert scope["type"] == "lifespan"
        message = await receive()
        assert message["type"] == "lifespan.startup"
        if self.fail_startup:
            await send({"type": "lifespan.startup.failed", "message": "db down"})
            return
        scope["state"]["ready"] = True
        self.events.append("startup")
        await send({"type": "lifespan.startup.complete"})
        message = await receive()
        assert message["type"] == "lifespan.shutdown"
        self.events.append("shutdown")
        if self.fail_shutdown:
            await send({"type": "lifespan.shutdown.failed", "message": "oops"})
        else:
            await send({"type": "lifespan.shutdown.complete"})


def test_lifespan_startup_and_shutdown(runtime: Runtime) -> None:
    app = LifespanApp()
    manager = LifespanManager(app)
    state = runtime.run(manager.startup())
    assert state == {"ready": True}
    assert manager.started
    runtime.run(manager.shutdown())
    assert app.events == ["startup", "shutdown"]


def test_lifespan_startup_failure(runtime: Runtime) -> None:
    manager = LifespanManager(LifespanApp(fail_startup=True))
    with pytest.raises(LifespanError, match="db down"):
        runtime.run(manager.startup())


def test_lifespan_shutdown_failure(runtime: Runtime) -> None:
    manager = LifespanManager(LifespanApp(fail_shutdown=True))
    runtime.run(manager.startup())
    with pytest.raises(LifespanError, match="oops"):
        runtime.run(manager.shutdown())


def test_app_without_lifespan_support_warns(runtime: Runtime) -> None:
    async def http_only(scope, receive, send) -> None:
        raise RuntimeError("only http")

    manager = LifespanManager(http_only)
    with pytest.warns(RuntimeWarning, match="does not support"):
        runtime.run(manager.startup())
    assert not manager.supported
    runtime.run(manager.shutdown())  # no-op


def test_lifespan_timeout(runtime: Runtime) -> None:
    async def hangs(scope, receive, send) -> None:
        await receive()
        await asyncio.sleep(3600)

    manager = LifespanManager(hangs, timeout=0.05)
    with pytest.raises(LifespanError, match="timed out"):
        runtime.run(manager.startup())


def test_fastapi_lifespan_state(runtime: Runtime) -> None:
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        events.append("up")
        yield {"db": "connected"}
        events.append("down")

    manager = LifespanManager(FastAPI(lifespan=lifespan))
    assert runtime.run(manager.startup()) == {"db": "connected"}
    runtime.run(manager.shutdown())
    assert events == ["up", "down"]
