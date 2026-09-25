"""The adapter interface that teaches fastapi-repl about an ORM.

To support a new ORM, subclass :class:`ORMAdapter`, override the hooks you
need, and register the class under the ``fastapi_repl.adapters`` entry point
group (or list its import path in the ``adapters`` setting). Every hook has a
sensible default, so a minimal adapter only needs ``name``, ``detect`` and
``discover_models``.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from rich.console import Console

    from fastapi_repl.config import ReplConfig
    from fastapi_repl.runtime import Runtime
    from fastapi_repl.sql import SQLPrinter


@dataclass(frozen=True)
class ModelInfo:
    """A model class discovered by an adapter."""

    cls: type
    name: str
    """The name the model gets in the shell (before aliases and collisions)."""
    module: str
    """The module the class is defined in."""
    adapter: str
    """Name of the adapter that found it."""
    prefix: str = ""
    """Prefix used when two models share a name (``collision = "prefix"``)."""
    label: str = ""
    """Optional group label, such as a Tortoise app label. Usable in ``dont_load``."""

    @property
    def qualname(self) -> str:
        return f"{self.module}.{self.name}"

    @classmethod
    def from_class(cls, model: type, adapter: str, *, label: str = "") -> ModelInfo:
        module = model.__module__
        parts = [p for p in module.split(".") if p not in {"models", "model", "__init__"}]
        prefix = label or (parts[-1] if parts else module.split(".")[-1])
        return cls(
            cls=model,
            name=model.__name__,
            module=module,
            adapter=adapter,
            prefix=prefix,
            label=label,
        )


@dataclass
class AdapterContext:
    """Everything an adapter can use. Passed to the adapter's constructor."""

    config: ReplConfig
    runtime: Runtime
    console: Console
    root: Path = field(default_factory=Path.cwd)
    """The project root."""
    modules: list[ModuleType] = field(default_factory=list)
    """Modules imported from the ``models`` setting, including submodules."""
    bases: list[Any] = field(default_factory=list)
    """Objects imported from the ``base`` setting."""
    app: Any = None
    """The ASGI app, if configured."""
    options: dict[str, Any] = field(default_factory=dict)
    """This adapter's ``[tool.fastapi-repl.plugins.<name>]`` table."""
    warn: Callable[[str], None] = print
    """Report a non-fatal problem to the user."""


class ORMAdapter:
    """Base class for ORM adapters.

    Lifecycle, in order:

    1. ``detect()`` (class method) decides whether the adapter applies.
    2. ``setup()`` runs on the session loop, e.g. to initialise connections.
    3. ``enable_read_only()`` if ``read_only`` is on.
    4. ``default_imports()``, ``discover_models()`` and ``objects()`` feed the
       namespace.
    5. ``enable_sql_echo()`` if ``--print-sql`` is on, after startup hooks ran.
    6. ``on_error()`` after each failed statement, while the shell is open.
    7. ``teardown()`` runs on the session loop when the shell exits.
    """

    name: ClassVar[str] = ""
    """Unique identifier, used in the ``adapters`` setting and plugin options."""
    display_name: ClassVar[str] = ""
    """Human friendly name for the banner."""
    package: ClassVar[str | None] = None
    """Import name of the ORM package, used by :meth:`is_installed`."""
    replaces: ClassVar[tuple[str, ...]] = ()
    """Adapters made redundant by this one (SQLModel replaces SQLAlchemy)."""

    def __init__(self, context: AdapterContext) -> None:
        self.context = context

    @property
    def config(self) -> ReplConfig:
        return self.context.config

    @classmethod
    def is_installed(cls) -> bool:
        """Return True if the ORM can be imported."""
        return cls.package is None or importlib.util.find_spec(cls.package) is not None

    @classmethod
    def detect(cls, context: AdapterContext) -> bool:
        """Return True if this project uses the ORM.

        Called after the app, ``models`` and ``base`` have been imported, so
        checking ``sys.modules`` is usually enough. Only used when the
        ``adapters`` setting is empty (auto-detection).
        """
        return cls.package is not None and cls.package in sys.modules

    @classmethod
    def version(cls) -> str | None:
        if cls.package is None:
            return None
        from importlib.metadata import PackageNotFoundError, packages_distributions
        from importlib.metadata import version as dist_version

        for dist in packages_distributions().get(cls.package, [cls.package]):
            try:
                return dist_version(dist)
            except PackageNotFoundError:
                continue
        return None

    def describe(self) -> str:
        """One-line description for the banner, e.g. ``SQLAlchemy 2.0 (async)``."""
        version = self.version()
        label = self.display_name or self.name
        return f"{label} {version}" if version else label

    def database(self) -> str | None:
        """Where the adapter is connected, for the banner. Never include passwords.

        Use :func:`mask_url` to render a URL safely.
        """
        return None

    async def setup(self) -> None:
        """Prepare the ORM. Runs once, before the namespace is built."""

    async def enable_read_only(self) -> None:
        """Make every connection read-only (the ``read_only`` setting).

        Raise an exception if that cannot be guaranteed: the shell then refuses
        to start rather than silently giving write access.
        """
        label = self.display_name or self.name
        raise NotImplementedError(f"The {label} adapter does not support read_only.")

    def on_error(self, error: BaseException) -> None:
        """Called after a statement typed in the shell raised ``error``.

        Use it to recover, e.g. roll back a session that can no longer be used.
        Only called when the ``rollback_on_error`` setting is on.
        """

    def discover_models(self) -> Iterable[ModelInfo]:
        """Yield the project's models."""
        return ()

    def default_imports(self) -> list[str]:
        """Import specs for helpers such as ``select`` or ``Q``.

        Skipped when the ``default_imports`` setting is false.
        """
        return []

    def objects(self) -> dict[str, Any]:
        """Ready-made objects such as ``engine`` and ``session``."""
        return {}

    def enable_sql_echo(self, printer: SQLPrinter) -> None:
        """Start printing SQL through ``printer``."""

    async def teardown(self) -> None:
        """Release resources. Runs once when the shell exits."""

    def tip(self, namespace: dict[str, Any]) -> str | None:
        """An example line of code for the banner, using names in ``namespace``."""
        return None


def mask_url(url: str) -> str:
    """Render a database URL without its password or query string.

    ``postgresql://app:secret@db:5432/app?sslkey=x`` becomes
    ``postgresql://app:***@db:5432/app``.
    """
    parts = urlsplit(url)
    if parts.password is None and not parts.query:
        return url
    netloc = parts.netloc.rpartition("@")[2]
    if parts.username is not None:
        userinfo = parts.username + (":***" if parts.password is not None else "")
        netloc = f"{userinfo}@{netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", parts.fragment))


def iter_classes(modules: Iterable[ModuleType]) -> Iterator[type]:
    """Yield each class found in ``modules`` once (including re-exported ones)."""
    seen: set[int] = set()
    for module in modules:
        for _, value in inspect.getmembers(module, inspect.isclass):
            if id(value) not in seen:
                seen.add(id(value))
                yield value
