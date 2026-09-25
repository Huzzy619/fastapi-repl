"""Builds and tears down a shell session.

:class:`ReplSession` is the heart of fastapi-repl. Every entry point (the
interactive shell, ``-c``, ``run``, ``imports``, :func:`fastapi_repl.embed`)
creates one, uses its namespace, and closes it.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
import warnings
from collections.abc import Callable, Iterable
from pathlib import Path
from types import ModuleType
from typing import Any

from rich.console import Console

from fastapi_repl.adapters import AdapterContext, ORMAdapter, select_adapters
from fastapi_repl.config import LoadedConfig, ReplConfig
from fastapi_repl.errors import CollisionError, ImportSpecError, ReplError
from fastapi_repl.imports import import_module, import_spec, import_string, resolve_object
from fastapi_repl.namespace import Namespace, is_excluded
from fastapi_repl.runtime import LifespanManager, Runtime
from fastapi_repl.sql import SQLPrinter


def walk_modules(name: str, on_error: Callable[[str, BaseException], None]) -> list[ModuleType]:
    """Import ``name`` and, if it is a package, all of its submodules."""
    module = import_module(name)
    modules = [module]
    path = getattr(module, "__path__", None)
    if path is None:
        return modules
    for info in pkgutil.walk_packages(path, prefix=f"{name}.", onerror=lambda n: None):
        try:
            modules.append(importlib.import_module(info.name))
        except Exception as exc:
            on_error(info.name, exc)
    return modules


async def _call_hook(func: Callable[..., Any], namespace: dict[str, Any]) -> Any:
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        params = {}
    positional = [
        p
        for p in params.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
    ]
    result = func(namespace) if positional else func()
    if inspect.isawaitable(result):
        result = await result
    return result


class ReplSession:
    """A fully prepared shell session.

    Use it as a context manager::

        with ReplSession(load_config()) as session:
            session.namespace.to_dict()

    Args:
        loaded: The resolved configuration.
        console: Console for the banner and warnings. Defaults to stdout.
        extra: Extra names added last (``embed()`` uses this for the caller's
            locals).
    """

    def __init__(
        self,
        loaded: LoadedConfig,
        *,
        console: Console | None = None,
        err_console: Console | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.loaded = loaded
        self.console = console or Console()
        self.err_console = err_console or Console(stderr=True)
        self.extra = extra or {}
        self.runtime: Runtime | None = None
        self.namespace = Namespace(
            collision=self.config.collision, model_aliases=self.config.model_aliases
        )
        self.adapters: list[ORMAdapter] = []
        self.lifespan: LifespanManager | None = None
        self.app: Any = None
        self.warnings: list[str] = list(loaded.warnings)
        self._added_paths: list[str] = []
        self._generator_closers: list[tuple[str, Callable[[], Any]]] = []
        self._started = False

    @property
    def config(self) -> ReplConfig:
        return self.loaded.config

    @property
    def root(self) -> Path:
        return self.loaded.root

    # Lifecycle

    def __enter__(self) -> ReplSession:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def _fail(self, what: str, group: str, error: BaseException) -> None:
        if self.config.strict or isinstance(error, CollisionError):
            if isinstance(error, ReplError):
                raise error
            raise ReplError(f"Could not load {what}: {type(error).__name__}: {error}") from error
        self.namespace.fail(what, group, error)

    def start(self) -> None:
        """Import everything and build the namespace."""
        if self._started:
            return
        self._started = True
        config = self.config
        self._setup_sys_path()
        self.runtime = runtime = Runtime()
        try:
            self._start(config, runtime)
        except BaseException:
            self.close()
            raise

    def _start(self, config: ReplConfig, runtime: Runtime) -> None:
        ns = self.namespace
        ns.add("await_", runtime.await_, group="builtins", source="fastapi-repl")

        if not config.auto_imports:
            if config.read_only:
                raise ReplError("read_only cannot be enforced with auto_imports = false.")
            self._add_extra()
            return

        for spec in config.pre_imports:
            self._import_into(spec, "pre_imports")

        # Import user code first so adapters can detect what is in use.
        if config.app:
            try:
                self.app = import_string(config.app)
            except Exception as exc:
                self._fail(config.app, "objects", exc)
        modules: list[ModuleType] = []
        for name in config.models:
            try:
                modules.extend(walk_modules(name, lambda n, e: self._fail(n, "models", e)))
            except Exception as exc:
                self._fail(name, "models", exc)
        bases: list[Any] = []
        for path in config.base:
            try:
                bases.append(import_string(path))
            except Exception as exc:
                self._fail(path, "models", exc)

        if config.lifespan:
            if self.app is None:
                self.warn("lifespan = true but no 'app' is configured; skipping lifespan.")
            else:
                self.lifespan = LifespanManager(self.app)
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    runtime.run(self.lifespan.startup())
                self.warnings.extend(str(w.message) for w in caught)

        context = AdapterContext(
            config=config,
            runtime=runtime,
            console=self.err_console,
            root=self.root,
            modules=modules,
            bases=bases,
            app=self.app,
            warn=self.warn,
        )
        for adapter in select_adapters(context):
            try:
                runtime.run(adapter.setup())
            except Exception as exc:
                self._fail(f"{adapter.name} adapter", "objects", exc)
                continue
            self.adapters.append(adapter)
            if config.read_only:
                try:
                    runtime.run(adapter.enable_read_only())
                except Exception as exc:
                    raise ReplError(
                        f"read_only is on, but it could not be enabled for {adapter.name}: {exc}"
                    ) from exc
        if config.read_only and not self.adapters:
            raise ReplError("read_only is on, but no ORM adapter is active to enforce it.")

        if config.default_imports:
            for adapter in self.adapters:
                for spec in adapter.default_imports():
                    self._import_into(spec, "helpers")

        if config.load_models:
            for adapter in self.adapters:
                try:
                    models = list(adapter.discover_models())
                except Exception as exc:
                    self._fail(f"{adapter.name} models", "models", exc)
                    continue
                for model in sorted(models, key=lambda m: (m.module, m.name)):
                    if not is_excluded(model, config.dont_load):
                        try:
                            ns.add_model(model)
                        except CollisionError as exc:
                            self._fail(model.qualname, "models", exc)

        if self.app is not None:
            ns.add("app", self.app, group="objects", source=config.app or "app")
        if self.lifespan is not None and self.lifespan.started:
            ns.add("lifespan_state", self.lifespan.state, group="objects", source="ASGI lifespan")
        for adapter in self.adapters:
            try:
                objects = adapter.objects()
            except Exception as exc:
                self._fail(f"{adapter.name} objects", "objects", exc)
                continue
            for name, value in objects.items():
                ns.add(name, value, group="objects", source=f"{adapter.name} adapter")

        for spec in config.imports:
            self._import_into(spec, "imports")

        for name, spec in config.objects.items():
            try:
                value, created = resolve_object(spec)
                if created:
                    value, created = self._materialise(value, spec)
            except Exception as exc:
                self._fail(f"{name} = {spec}", "objects", exc)
                continue
            ns.add(name, value, group="objects", source=spec, created=created)

        for path in config.hooks.namespace:
            try:
                hook = import_string(path)
                result = runtime.run(_call_hook(hook, ns.to_dict()))
            except Exception as exc:
                self._fail(f"hook {path}", "hooks", exc)
                continue
            if result is None:
                continue
            if not isinstance(result, dict):
                self._fail(f"hook {path}", "hooks", TypeError("must return a dict or None"))
                continue
            for name, value in result.items():
                ns.add(name, value, group="hooks", source=path)

        for spec in config.post_imports:
            self._import_into(spec, "post_imports")

        self._add_extra()

        for path in config.hooks.startup:
            try:
                runtime.run(_call_hook(import_string(path), ns.to_dict()))
            except Exception as exc:
                self._fail(f"startup hook {path}", "hooks", exc)

        # Enabled last so SQL from startup hooks does not flood the banner.
        if config.print_sql:
            printer = SQLPrinter(
                self.err_console,
                truncate=config.truncate_sql,
                location=config.print_sql_location,
            )
            for adapter in self.adapters:
                adapter.enable_sql_echo(printer)

        if config.rollback_on_error:
            runtime.error_hooks.extend(adapter.on_error for adapter in self.adapters)

    def _add_extra(self) -> None:
        for name, value in self.extra.items():
            self.namespace.add(name, value, group="extra", source="embed()")

    def _import_into(self, spec: str, group: str, *, source_prefix: str = "") -> None:
        try:
            names = import_spec(spec)
        except Exception as exc:
            self._fail(spec, group, exc)
            return
        for item in names:
            value, created = item.value, item.created
            if created:
                try:
                    value, created = self._materialise(value, spec)
                except Exception as exc:
                    self._fail(spec, group, exc)
                    continue
            self.namespace.add(
                item.name,
                value,
                group=group,
                source=source_prefix + item.source,
                created=created,
            )

    def _materialise(self, value: Any, spec: str) -> tuple[Any, bool]:
        """Turn a factory's return value into the object the shell gets.

        Awaitables are awaited. Generators (FastAPI-style dependencies such as
        ``async def get_db(): async with Session() as s: yield s``) are advanced
        to their first value and closed on exit. Closing runs ``finally`` blocks
        and ``with`` exits, but not code after the ``yield``, so leaving the
        shell never commits on your behalf.

        Returns:
            ``(value, created)``. ``created`` is False for generator values,
            because the generator owns their cleanup.
        """
        assert self.runtime is not None
        if inspect.isasyncgen(value):
            try:
                result = self.runtime.run(anext(value))
            except StopAsyncIteration:
                raise ImportSpecError(f"'{spec}' did not yield a value.") from None
            self._generator_closers.append((spec, value.aclose))
            return result, False
        if inspect.isgenerator(value):
            try:
                result = next(value)
            except StopIteration:
                raise ImportSpecError(f"'{spec}' did not yield a value.") from None
            self._generator_closers.append((spec, value.close))
            return result, False
        return self.runtime.resolve(value), True

    def _setup_sys_path(self) -> None:
        for entry in reversed(self.config.pythonpath):
            path = str((self.root / entry).resolve())
            if path not in sys.path:
                sys.path.insert(0, path)
                self._added_paths.append(path)

    def close(self) -> None:
        """Run shutdown hooks, close created objects, adapters and the lifespan."""
        runtime = self.runtime
        if runtime is None or runtime.closed:
            self._restore_sys_path()
            return
        errors: list[str] = []
        runtime.error_hooks.clear()

        def attempt(label: str, func: Callable[[], Any]) -> None:
            try:
                runtime.resolve(func())
            except Exception as exc:
                errors.append(f"{label}: {type(exc).__name__}: {exc}")

        namespace = self.namespace.to_dict()
        for path in self.config.hooks.shutdown:
            attempt(
                f"shutdown hook {path}",
                lambda p=path: _call_hook(import_string(p), namespace),
            )
        for value in reversed(self.namespace.created_values()):
            closer = getattr(value, "aclose", None) or getattr(value, "close", None)
            if callable(closer):
                attempt(f"closing {type(value).__name__}", closer)
        for spec, close_generator in reversed(self._generator_closers):
            attempt(f"closing {spec}", close_generator)
        self._generator_closers.clear()
        for adapter in reversed(self.adapters):
            attempt(f"{adapter.name} teardown", adapter.teardown)
        if self.lifespan is not None:
            attempt("lifespan shutdown", self.lifespan.shutdown)
        try:
            runtime.close()
        finally:
            self._restore_sys_path()
        for message in errors:
            self.err_console.print(f"[yellow]warning:[/] {message}")

    def _restore_sys_path(self) -> None:
        for path in self._added_paths:
            if path in sys.path:
                sys.path.remove(path)
        self._added_paths.clear()

    # Introspection helpers used by the banner and CLI

    def tips(self) -> Iterable[str]:
        namespace = self.namespace.to_dict()
        for adapter in self.adapters:
            try:
                tip = adapter.tip(namespace)
            except Exception:
                tip = None
            if tip:
                yield tip
