"""bpython interface."""

from __future__ import annotations

from fastapi_repl.interfaces.base import Interface


class BpythonInterface(Interface):
    """bpython. It has no top-level ``await``; use ``await_(coro)`` instead."""

    name = "bpython"
    display_name = "bpython"
    package = "bpython"
    distribution = "bpython"
    supports_await = False

    def start(self) -> None:
        import bpython

        bpython.embed(locals_=self.context.namespace, args=[], banner="")
