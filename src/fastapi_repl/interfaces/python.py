"""The plain Python interface: the standard REPL plus top-level ``await``."""

from __future__ import annotations

import atexit
import code
import inspect
import os
import sys
import types
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi_repl.execute import TOP_LEVEL_AWAIT, compile_source
from fastapi_repl.interfaces.base import Interface, private_file
from fastapi_repl.runtime import Runtime


class AsyncConsole(code.InteractiveConsole):
    """``code.InteractiveConsole`` that understands top-level ``await``.

    Works like ``python -m asyncio``, except coroutines run on the shell's
    shared :class:`~fastapi_repl.runtime.Runtime` loop.
    """

    def __init__(
        self, namespace: dict[str, Any], runtime: Runtime, filename: str = "<console>"
    ) -> None:
        super().__init__(namespace, filename)
        self.runtime = runtime
        self.compile.compiler.flags |= TOP_LEVEL_AWAIT

    def runcode(self, code: types.CodeType) -> None:
        try:
            if code.co_flags & inspect.CO_COROUTINE:
                self.runtime.run(types.FunctionType(code, self.locals)())
            else:
                exec(code, self.locals)
        except SystemExit:
            raise
        except BaseException as exc:
            self.showtraceback()
            self.runtime.report_error(exc)


def _setup_readline(namespace: dict[str, Any]) -> None:
    try:
        import readline
        import rlcompleter
    except ImportError:
        return
    readline.set_completer(rlcompleter.Completer(namespace).complete)
    if "libedit" in (readline.__doc__ or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
    history = private_file(Path.home() / ".cache" / "fastapi-repl" / "python_history")
    if history is None:
        return
    try:
        readline.read_history_file(history)
    except OSError:
        return
    readline.set_history_length(5000)
    atexit.register(_write_history, readline, history)


def _write_history(readline: Any, history: Path) -> None:
    with suppress(OSError):
        readline.write_history_file(history)


def run_startup_files(namespace: dict[str, Any], runtime: Runtime) -> None:
    """Run ``$PYTHONSTARTUP`` and ``~/.pythonrc.py``, like Django's shell."""
    candidates = [os.environ.get("PYTHONSTARTUP"), str(Path.home() / ".pythonrc.py")]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if not path.is_file() or str(path.resolve()) in seen:
            continue
        seen.add(str(path.resolve()))
        try:
            source = path.read_text(encoding="utf-8")
            compiled = compile_source(source, str(path))
            if compiled.co_flags & inspect.CO_COROUTINE:
                runtime.run(eval(compiled, namespace))
            else:
                exec(compiled, namespace)
        except Exception:
            import traceback

            print(f"Error running startup file {path}:", file=sys.stderr)
            traceback.print_exc()


class PythonInterface(Interface):
    """The standard Python REPL with top-level ``await`` and tab completion."""

    name = "python"
    display_name = "Python"
    package = None

    @classmethod
    def describe(cls) -> str:
        return f"Python {sys.version.split()[0]}"

    def start(self) -> None:
        namespace = self.context.namespace
        runtime = self.context.runtime
        _setup_readline(namespace)
        if self.context.loaded.config.startup:
            run_startup_files(namespace, runtime)
        console = AsyncConsole(namespace, runtime)
        console.interact(banner="", exitmsg="")
