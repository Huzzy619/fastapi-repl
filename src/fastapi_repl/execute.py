"""Run source code (``-c``, stdin, ``run SCRIPT``) with top-level ``await`` support."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from pathlib import Path
from types import CodeType
from typing import Any

from fastapi_repl.errors import ReplError
from fastapi_repl.runtime import Runtime

TOP_LEVEL_AWAIT = ast.PyCF_ALLOW_TOP_LEVEL_AWAIT


def compile_source(source: str, filename: str, mode: str = "exec") -> CodeType:
    """Compile ``source`` allowing ``await``, ``async for`` and ``async with`` at top level."""
    return compile(source, filename, mode, flags=TOP_LEVEL_AWAIT, dont_inherit=True)


def run_code(code: CodeType, namespace: dict[str, Any], runtime: Runtime) -> Any:
    """Execute compiled code, awaiting it on the session loop if it uses ``await``."""
    if code.co_flags & inspect.CO_COROUTINE:
        return runtime.run(eval(code, namespace))
    return eval(code, namespace)


def run_source(
    source: str, namespace: dict[str, Any], runtime: Runtime, filename: str = "<command>"
) -> None:
    """Compile and run a block of source code in ``namespace``."""
    run_code(compile_source(source, filename), namespace, runtime)


def resolve_script(target: str) -> Path:
    """Turn a file path or dotted module name into a script path."""
    path = Path(target)
    if path.suffix == ".py" or path.exists():
        if not path.is_file():
            raise ReplError(f"Script {target} does not exist.")
        return path.resolve()
    try:
        spec = importlib.util.find_spec(target)
    except (ImportError, ValueError) as exc:
        raise ReplError(f"Cannot find script or module '{target}': {exc}") from None
    if spec is None:
        raise ReplError(f"Cannot find script or module '{target}'.")
    if spec.submodule_search_locations is not None:
        spec = importlib.util.find_spec(f"{target}.__main__") or spec
    if not spec.origin or not spec.origin.endswith(".py"):
        raise ReplError(f"'{target}' does not point to a Python source file.")
    return Path(spec.origin)


def run_script(
    path: Path,
    namespace: dict[str, Any],
    runtime: Runtime,
    *,
    argv: list[str] | None = None,
    func: str | None = None,
) -> Any:
    """Run a script file as ``__main__`` with the shell namespace available.

    The script can use top-level ``await``. If ``func`` is given, that function
    (sync or async) is called after the script body runs, like django-extensions'
    ``runscript``.
    """
    source = path.read_text(encoding="utf-8")
    globals_ = dict(namespace)
    globals_.update({"__name__": "__main__", "__file__": str(path), "__builtins__": __builtins__})
    old_argv = sys.argv
    sys.argv = [str(path), *(argv or [])]
    sys.path.insert(0, str(path.parent))
    try:
        run_code(compile_source(source, str(path)), globals_, runtime)
        if func:
            target = globals_.get(func)
            if not callable(target):
                raise ReplError(f"{path.name} has no function named '{func}'.")
            return runtime.resolve(target())
        return None
    finally:
        sys.argv = old_argv
        if sys.path and sys.path[0] == str(path.parent):
            sys.path.pop(0)
