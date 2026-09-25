"""ptpython and ptipython interfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn

from fastapi_repl.interfaces.base import Interface, private_file


def _history_file(name: str) -> str | None:
    path = private_file(Path.home() / ".cache" / "fastapi-repl" / f"{name}_history")
    return str(path) if path is not None else None


class _Exit:
    def __call__(self) -> NoReturn:
        raise SystemExit

    def __repr__(self) -> str:
        return "Use exit() or Ctrl-D (i.e. EOF) to exit"


class PtpythonInterface(Interface):
    """ptpython, run as a coroutine on the session loop.

    Because the prompt itself runs inside the loop, top-level ``await`` is
    native and background tasks keep running between prompts.
    """

    name = "ptpython"
    display_name = "ptpython"
    package = "ptpython"
    distribution = "ptpython"

    def start(self) -> None:
        from ptpython.repl import embed, run_config

        def configure(repl: Any) -> None:
            run_config(repl)
            add_to_namespace = repl._add_to_namespace

            # ptpython's exit() raises ReplExit, which its asyncio loop does not
            # handle; SystemExit ends the REPL cleanly.
            def patched() -> None:
                add_to_namespace()
                repl.get_globals()["exit"] = repl.get_globals()["quit"] = _Exit()

            repl._add_to_namespace = patched

        namespace = self.context.namespace
        coro = embed(
            globals=namespace,
            locals=namespace,
            configure=configure,
            history_filename=_history_file("ptpython"),
            title="fastapi-repl",
            patch_stdout=True,
            return_asyncio_coroutine=True,
        )
        assert coro is not None
        self.context.runtime.run(coro)


class _NamespaceModule:
    """Stand-in module whose ``__dict__`` is the shell namespace (IPython's ``module=``)."""


class PtipythonInterface(Interface):
    """ptpython's prompt on top of IPython (magics, ``?`` help...)."""

    name = "ptipython"
    display_name = "ptipython"
    package = "ptpython"
    distribution = "ptpython"

    @classmethod
    def is_available(cls) -> bool:
        import importlib.util

        return super().is_available() and importlib.util.find_spec("IPython") is not None

    @classmethod
    def install_hint(cls) -> str:
        return "pip install 'fastapi-repl[ptpython,ipython]'"

    def start(self) -> None:
        from ptpython.ipython import InteractiveShellEmbed
        from ptpython.repl import run_config

        namespace = self.context.namespace
        module = _NamespaceModule()
        module.__dict__ = namespace
        shell = InteractiveShellEmbed(
            configure=run_config,
            history_filename=_history_file("ptipython"),
            display_banner=False,
        )
        shell.autoawait = True
        shell.loop_runner = self.context.runtime.run
        try:
            shell(local_ns=namespace, module=module)
        finally:
            InteractiveShellEmbed.clear_instance()
