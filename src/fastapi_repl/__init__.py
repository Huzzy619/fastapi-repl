"""fastapi-repl: a Django shell_plus style shell for FastAPI and other ASGI projects.

Most people only use the ``fastapi-repl`` command. The Python API is for
embedding a shell in your own code or CLI:

* :func:`embed` opens a shell with the caller's variables plus the project namespace.
* :data:`cli` is the Typer app, so you can mount it in your own Typer CLI.
* :class:`ORMAdapter` is the base class for supporting another ORM.
"""

from fastapi_repl.__about__ import __version__
from fastapi_repl.adapters.base import AdapterContext, ModelInfo, ORMAdapter
from fastapi_repl.api import build_namespace, embed, start_shell
from fastapi_repl.cli import app as cli
from fastapi_repl.config import LoadedConfig, ReplConfig, load_config
from fastapi_repl.errors import ReplError
from fastapi_repl.runtime import LifespanManager, Runtime
from fastapi_repl.session import ReplSession
from fastapi_repl.sql import SQLPrinter

__all__ = [
    "AdapterContext",
    "LifespanManager",
    "LoadedConfig",
    "ModelInfo",
    "ORMAdapter",
    "ReplConfig",
    "ReplError",
    "ReplSession",
    "Runtime",
    "SQLPrinter",
    "__version__",
    "build_namespace",
    "cli",
    "embed",
    "load_config",
    "start_shell",
]
