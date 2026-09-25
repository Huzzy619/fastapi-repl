"""Parse and execute import specs.

An *import spec* is a string that says what to put in the shell. Three forms
are accepted:

* A Python import statement: ``"from sqlalchemy import select, func"``,
  ``"import datetime as dt"``, ``"from app.models import *"``. Several
  statements can be separated with ``;``.
* An object path: ``"app.core.config:settings"`` binds ``settings``. Attribute
  chains work too (``"app.main:app.state"`` binds ``state``), and a trailing
  ``()`` calls the object with no arguments (``"app.db:get_session()"``).
* A bare module name: ``"json"`` is the same as ``"import json"``.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from fastapi_repl.errors import ImportSpecError

_OBJECT_PATH = re.compile(r"^(?P<module>[A-Za-z_][\w.]*):(?P<attr>[A-Za-z_][\w.]*)(?P<call>\(\))?$")
_MODULE_PATH = re.compile(r"^[A-Za-z_][\w.]*$")


@dataclass(frozen=True)
class ImportedName:
    """One name produced by an import spec."""

    name: str
    value: Any
    source: str
    """A human readable description, e.g. ``from sqlalchemy import select``."""
    created: bool = False
    """True when the value was created by calling a factory (``module:factory()``)."""


def is_statement(spec: str) -> bool:
    stripped = spec.lstrip()
    return stripped.startswith(("import ", "from "))


def import_module(name: str) -> ModuleType:
    """Import a module, with a friendlier error message."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name and (name == exc.name or name.startswith(exc.name + ".")):
            hint = ""
            if "." not in sys.path and "" not in sys.path:
                hint = " Is the project root on sys.path? Check the 'pythonpath' setting."
            raise ImportSpecError(f"No module named '{exc.name}'.{hint}") from exc
        raise


def _getattr_chain(obj: Any, chain: str, *, origin: str) -> Any:
    for part in chain.split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError:
            raise ImportSpecError(f"'{origin}' has no attribute '{part}'.") from None
    return obj


def import_string(path: str) -> Any:
    """Import an object from ``"module:attr"`` or ``"module.attr"``.

    The colon form is unambiguous and preferred. With the dotted form, the
    longest importable module prefix is used.
    """
    path = path.strip()
    match = _OBJECT_PATH.match(path)
    if match and not match.group("call"):
        module = import_module(match.group("module"))
        return _getattr_chain(module, match.group("attr"), origin=match.group("module"))
    if _MODULE_PATH.match(path):
        parts = path.split(".")
        for i in range(len(parts), 0, -1):
            module_name = ".".join(parts[:i])
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError as exc:
                if exc.name and module_name.startswith(exc.name):
                    continue
                raise
            rest = ".".join(parts[i:])
            return _getattr_chain(module, rest, origin=module_name) if rest else module
        raise ImportSpecError(f"No module named '{parts[0]}'.")
    raise ImportSpecError(f"'{path}' is not a valid import path. Use 'package.module:attribute'.")


def resolve_object(spec: str) -> tuple[Any, bool]:
    """Resolve an object path, calling it if the spec ends with ``()``.

    Returns:
        ``(value, created)`` where ``created`` says whether a factory was called.
        The value may be awaitable; the caller is responsible for awaiting it.
    """
    spec = spec.strip()
    match = _OBJECT_PATH.match(spec)
    if match and match.group("call"):
        factory = import_string(f"{match.group('module')}:{match.group('attr')}")
        if not callable(factory):
            raise ImportSpecError(f"'{spec[:-2]}' is not callable.")
        return factory(), True
    return import_string(spec), False


def _statement_names(spec: str) -> list[ImportedName]:
    try:
        tree = ast.parse(spec.strip(), mode="exec")
    except SyntaxError as exc:
        raise ImportSpecError(f"'{spec}' is not a valid import statement: {exc.msg}.") from None

    results: list[ImportedName] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = import_module(alias.name)
                if alias.asname:
                    results.append(
                        ImportedName(alias.asname, module, f"import {alias.name} as {alias.asname}")
                    )
                else:
                    top = alias.name.split(".")[0]
                    results.append(ImportedName(top, sys.modules[top], f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise ImportSpecError(
                    f"Relative imports are not supported in '{spec}'. Use an absolute import."
                )
            assert node.module is not None
            module = import_module(node.module)
            for alias in node.names:
                if alias.name == "*":
                    results.extend(_star_names(module, node.module))
                    continue
                if hasattr(module, alias.name):
                    value = getattr(module, alias.name)
                else:
                    value = import_module(f"{node.module}.{alias.name}")
                name = alias.asname or alias.name
                source = f"from {node.module} import {alias.name}"
                if alias.asname:
                    source += f" as {alias.asname}"
                results.append(ImportedName(name, value, source))
        else:
            raise ImportSpecError(f"'{spec}' may only contain import statements.")
    return results


def _star_names(module: ModuleType, module_name: str) -> list[ImportedName]:
    names = getattr(module, "__all__", None)
    if names is None:
        names = [n for n in vars(module) if not n.startswith("_")]
    source = f"from {module_name} import *"
    return [ImportedName(name, getattr(module, name), source) for name in names]


def import_spec(spec: str) -> list[ImportedName]:
    """Execute an import spec and return the names it produces.

    Raises:
        ImportSpecError: If the spec is malformed or refers to something missing.
        Exception: Any error raised while importing the user's modules.
    """
    if not isinstance(spec, str) or not spec.strip():
        raise ImportSpecError(f"Import specs must be non-empty strings, got {spec!r}.")
    spec = spec.strip()
    if is_statement(spec):
        return _statement_names(spec)
    if ":" in spec:
        value, created = resolve_object(spec)
        attr = spec.split(":", 1)[1].removesuffix("()")
        name = attr.split(".")[-1]
        return [ImportedName(name, value, spec, created=created)]
    if _MODULE_PATH.match(spec):
        return _statement_names(f"import {spec}")
    raise ImportSpecError(
        f"Cannot understand import spec '{spec}'. Use an import statement "
        "('from x import y'), an object path ('x:y') or a module name ('x')."
    )
