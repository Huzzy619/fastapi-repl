from __future__ import annotations

import asyncio
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import FIXTURES

from fastapi_repl.config import load_config
from fastapi_repl.errors import ConfigError, InterfaceUnavailableError
from fastapi_repl.interfaces import INTERFACES, AsyncConsole, InterfaceContext, select_interface
from fastapi_repl.interfaces.bpython import BpythonInterface
from fastapi_repl.interfaces.ipython import IPythonInterface
from fastapi_repl.interfaces.ptpython import PtpythonInterface
from fastapi_repl.interfaces.python import PythonInterface, run_startup_files
from fastapi_repl.runtime import Runtime

POSIX = sys.platform != "win32"


@pytest.fixture
def runtime():
    rt = Runtime()
    yield rt
    rt.close()


def make_context(
    runtime: Runtime, tmp_path: Path, namespace: dict[str, Any] | None = None, **config: Any
) -> InterfaceContext:
    from rich.console import Console

    loaded = load_config(cwd=tmp_path, environ={}, cli=config)
    return InterfaceContext(
        namespace=namespace if namespace is not None else {},
        runtime=runtime,
        loaded=loaded,
        console=Console(),
    )


def test_auto_picks_first_available(monkeypatch) -> None:
    monkeypatch.setattr(IPythonInterface, "is_available", classmethod(lambda cls: False))
    assert select_interface("auto", ["ipython", "ptpython", "python"]) is PtpythonInterface


def test_auto_falls_back_to_python(monkeypatch) -> None:
    for cls in INTERFACES.values():
        if cls is not PythonInterface:
            monkeypatch.setattr(cls, "is_available", classmethod(lambda cls: False))
    assert select_interface("auto", ["ipython", "bpython"]) is PythonInterface


def test_specific_interface_not_installed(monkeypatch) -> None:
    monkeypatch.setattr(BpythonInterface, "is_available", classmethod(lambda cls: False))
    with pytest.raises(InterfaceUnavailableError, match=r"fastapi-repl\[bpython\]"):
        select_interface("bpython", [])


def test_unknown_interface() -> None:
    with pytest.raises(ConfigError):
        select_interface("emacs", [])
    with pytest.raises(ConfigError):
        select_interface("auto", ["emacs"])


def test_async_console_supports_await(runtime: Runtime) -> None:
    namespace: dict[str, Any] = {"asyncio": asyncio, "LOOP": object()}
    console = AsyncConsole(namespace, runtime)
    out = io.StringIO()
    with redirect_stdout(out):
        console.push("loop = await asyncio.sleep(0, asyncio.get_running_loop())")
        console.push("print(loop is LOOP)")
        console.push("async def twice(x):")
        console.push("    return x * 2")
        console.push("")
        console.push("print(await twice(21))")
    namespace["LOOP"] = runtime.loop
    with redirect_stdout(out):
        console.push("print(loop is LOOP)")
    assert out.getvalue().splitlines() == ["False", "42", "True"]


def test_async_console_shows_errors(runtime: Runtime, capsys) -> None:
    console = AsyncConsole({}, runtime)
    console.push("await undefined_name")
    assert "NameError" in capsys.readouterr().err


def test_startup_files(tmp_path: Path, runtime: Runtime, monkeypatch) -> None:
    startup = tmp_path / "startup.py"
    startup.write_text("import asyncio\nFROM_STARTUP = await asyncio.sleep(0, 'yes')\n")
    monkeypatch.setenv("PYTHONSTARTUP", str(startup))
    monkeypatch.setenv("HOME", str(tmp_path))
    namespace: dict[str, Any] = {}
    run_startup_files(namespace, runtime)
    assert namespace["FROM_STARTUP"] == "yes"


def test_ipython_runs_await_on_session_loop(runtime: Runtime, tmp_path: Path) -> None:
    namespace: dict[str, Any] = {"LOOP": runtime.loop}
    code = "import asyncio\nSAME = (await asyncio.sleep(0, asyncio.get_running_loop())) is LOOP"
    context = make_context(
        runtime, tmp_path, namespace, ipython_arguments=["--no-banner", "-c", code]
    )
    interface = IPythonInterface(context)
    interface.start()
    assert namespace["SAME"] is True


def test_ptpython_embed_runs_on_session_loop(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    seen: dict[str, Any] = {}

    async def fake_embed(**kwargs: Any) -> None:
        seen["loop"] = asyncio.get_running_loop()
        seen["kwargs"] = kwargs

    import ptpython.repl

    monkeypatch.setattr(ptpython.repl, "embed", lambda **kw: fake_embed(**kw))
    namespace = {"x": 1}
    PtpythonInterface(make_context(runtime, tmp_path, namespace)).start()
    assert seen["loop"] is runtime.loop
    assert seen["kwargs"]["globals"] is namespace
    assert seen["kwargs"]["return_asyncio_coroutine"] is True


def test_ptpython_exit_ends_repl_cleanly(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_embed(**kwargs: Any) -> None:
        class FakeRepl:
            def __init__(self) -> None:
                self.globals: dict[str, Any] = {}

            def get_globals(self) -> dict[str, Any]:
                return self.globals

            def _add_to_namespace(self) -> None:
                self.globals["exit"] = "ptpython exit"

        repl = FakeRepl()
        monkeypatch.setattr("ptpython.repl.run_config", lambda repl: None)
        kwargs["configure"](repl)
        repl._add_to_namespace()
        captured["exit"] = repl.globals["exit"]

    monkeypatch.setattr("ptpython.repl.embed", lambda **kw: fake_embed(**kw))
    PtpythonInterface(make_context(runtime, tmp_path)).start()
    with pytest.raises(SystemExit):
        captured["exit"]()


def test_bpython_gets_namespace(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    bpython = pytest.importorskip("bpython")

    monkeypatch.setattr(bpython, "embed", lambda **kw: calls.append(kw))
    namespace = {"x": 1}
    BpythonInterface(make_context(runtime, tmp_path, namespace)).start()
    assert calls[0]["locals_"] is namespace
    assert BpythonInterface.supports_await is False


def test_kernel_interface(runtime: Runtime, tmp_path: Path, monkeypatch) -> None:
    from fastapi_repl.interfaces.jupyter import KernelInterface

    created: dict[str, Any] = {}

    class FakeApp:
        @classmethod
        def instance(cls, **kwargs: Any) -> FakeApp:
            created["kwargs"] = kwargs
            return cls()

        @classmethod
        def clear_instance(cls) -> None:
            created["cleared"] = True

        def initialize(self, argv: list[str]) -> None:
            created["argv"] = argv

        def start(self) -> None:
            created["started"] = True

    monkeypatch.setattr("ipykernel.kernelapp.IPKernelApp", FakeApp)
    namespace = {"x": 1}
    KernelInterface(make_context(runtime, tmp_path, namespace), connection_file="c.json").start()
    assert created["kwargs"]["user_ns"] is namespace
    assert created["argv"] == ["-f", "c.json"]
    assert created["started"]
    assert created["cleared"]


# Real terminal sessions ----------------------------------------------------


@pytest.mark.skipif(not POSIX, reason="needs a pseudo-terminal")
@pytest.mark.parametrize("interface", ["python", "ipython", "ptpython"])
def test_interactive_session(interface: str, tmp_path: Path) -> None:
    import shutil

    from tests.pty_driver import run_interactive

    root = tmp_path / "sa_async"
    shutil.copytree(FIXTURES / "sa_async", root)
    output = run_interactive(
        ["-i", interface],
        [
            "n = await session.scalar(select(func.count(User.id)))",
            "print('RESULT', n * 21)",
            "exit()",
        ],
        cwd=root,
    )
    assert "fastapi-repl" in output
    assert "Models (4)" in output
    assert "RESULT 42" in output
    assert "Traceback" not in output
