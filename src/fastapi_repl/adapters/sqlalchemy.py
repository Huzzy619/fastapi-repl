"""SQLAlchemy 2.x adapter (sync and async)."""

from __future__ import annotations

import gc
import sys
import time
from collections.abc import Iterable, Iterator
from typing import Any

from fastapi_repl.adapters.base import ModelInfo, ORMAdapter, iter_classes
from fastapi_repl.imports import import_string
from fastapi_repl.sql import SQLPrinter, find_caller

_START_KEY = "_fastapi_repl_query_start"


class SQLAlchemyAdapter(ORMAdapter):
    """Loads SQLAlchemy models, an engine and a session.

    * Models come from the registry of each ``base`` class, plus every mapped
      class found in the ``models`` modules (and the other models registered
      alongside them).
    * The engine comes from ``sqlalchemy.engine`` or is auto-detected.
    * ``session`` is an ``AsyncSession`` for async engines and a ``Session``
      otherwise, or whatever ``sqlalchemy.session_factory`` returns.
    """

    name = "sqlalchemy"
    display_name = "SQLAlchemy"
    package = "sqlalchemy"

    def __init__(self, context: Any) -> None:
        super().__init__(context)
        self.engine: Any = None
        self.engine_detected = False
        self.session: Any = None
        self.read_only = False
        self._listeners: list[tuple[Any, str, Any]] = []

    @classmethod
    def detect(cls, context: Any) -> bool:
        if context.config.sqlalchemy.engine or context.config.sqlalchemy.session_factory:
            return True
        if "sqlalchemy.orm" not in sys.modules:
            return False
        if any(hasattr(getattr(b, "registry", None), "mappers") for b in context.bases):
            return True
        if any(_is_mapped(c) for c in iter_classes(context.modules)):
            return True
        return any(_is_live(m.class_) for r in cls._all_registries() for m in r.mappers)

    # Engine and session

    @property
    def options(self) -> Any:
        return self.config.sqlalchemy

    @property
    def is_async(self) -> bool:
        from sqlalchemy.ext.asyncio import AsyncEngine

        return isinstance(self.engine, AsyncEngine)

    def describe(self) -> str:
        text = super().describe()
        if self.engine is not None:
            text += " (async)" if self.is_async else " (sync)"
        return text

    def database(self) -> str | None:
        if self.engine is None:
            return None
        return self.engine.url.set(query={}).render_as_string(hide_password=True)

    @property
    def sync_engine(self) -> Any:
        return getattr(self.engine, "sync_engine", self.engine)

    async def setup(self) -> None:
        if self.options.engine:
            self.engine = import_string(self.options.engine)
        else:
            self.engine = self._find_engine()
            self.engine_detected = self.engine is not None

    def _find_engine(self) -> Any:
        """Find the single Engine/AsyncEngine in memory, if there is exactly one."""
        from sqlalchemy.engine import Engine
        from sqlalchemy.ext.asyncio import AsyncEngine

        async_engines: list[Any] = []
        engines: list[Any] = []
        for obj in gc.get_objects():
            try:
                if isinstance(obj, AsyncEngine):
                    async_engines.append(obj)
                elif isinstance(obj, Engine):
                    engines.append(obj)
            except ReferenceError:
                continue
        wrapped = {id(e.sync_engine) for e in async_engines}
        engines = [e for e in engines if id(e) not in wrapped]
        candidates = async_engines + engines
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            self.context.warn(
                f"Found {len(candidates)} SQLAlchemy engines; set "
                "[tool.fastapi-repl.sqlalchemy] engine = 'module:engine' to pick one."
            )
        return None

    def make_session(self) -> Any:
        if self.options.session_factory:
            factory = import_string(self.options.session_factory)
            return factory()
        if self.engine is None:
            return None
        if self.is_async:
            from sqlalchemy.ext.asyncio import AsyncSession

            return AsyncSession(self.engine, expire_on_commit=False)
        from sqlalchemy.orm import Session

        return Session(self.engine)

    def objects(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.engine is not None:
            result[self.options.engine_name] = self.engine
        if self.options.session and self.options.session_name not in self.config.objects:
            self.session = self.make_session()
            if self.session is not None:
                result[self.options.session_name] = self.session
        return result

    # Models

    def registries(self) -> list[Any]:
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy.orm import Mapper

        found: dict[int, Any] = {}
        for base in self.context.bases:
            registry = getattr(base, "registry", None)
            if registry is not None and hasattr(registry, "mappers"):
                found[id(registry)] = registry
        for cls in iter_classes(self.context.modules):
            mapper = sa_inspect(cls, raiseerr=False)
            if isinstance(mapper, Mapper):
                found.setdefault(id(mapper.registry), mapper.registry)
        if not found:
            found.update({id(r): r for r in self._all_registries()})
        return list(found.values())

    @staticmethod
    def _all_registries() -> Iterable[Any]:
        try:
            from sqlalchemy.orm.mapper import _mapper_registries
        except ImportError:  # pragma: no cover - private API moved
            return []
        return list(_mapper_registries)

    def iter_mapped_classes(self) -> Iterator[type]:
        seen: set[int] = set()
        for registry in self.registries():
            for mapper in registry.mappers:
                cls = mapper.class_
                if id(cls) not in seen and _is_live(cls):
                    seen.add(id(cls))
                    yield cls

    def discover_models(self) -> Iterable[ModelInfo]:
        for cls in self.iter_mapped_classes():
            yield ModelInfo.from_class(cls, self.name)

    def default_imports(self) -> list[str]:
        imports = [
            "from sqlalchemy import select, insert, update, delete, func, text, and_, or_, not_, "
            "desc, asc, case, cast, literal, exists",
            "from sqlalchemy import inspect as sa_inspect",
            "from sqlalchemy.orm import selectinload, joinedload, load_only, aliased",
        ]
        if self.is_async:
            imports.append("from sqlalchemy.ext.asyncio import AsyncSession")
        else:
            imports.append("from sqlalchemy.orm import Session")
        return imports

    # SQL echo

    def enable_sql_echo(self, printer: SQLPrinter) -> None:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        def before(conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool):
            conn.info.setdefault(_START_KEY, []).append(
                (time.perf_counter(), find_caller() if printer.location else None)
            )

        def after(conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool):
            stack = conn.info.get(_START_KEY) or [(None, None)]
            started, caller = stack.pop()
            duration = time.perf_counter() - started if started is not None else None
            printer(statement, params, duration=duration, many=many, caller=caller)

        for name, fn in (("before_cursor_execute", before), ("after_cursor_execute", after)):
            event.listen(Engine, name, fn)
            self._listeners.append((Engine, name, fn))

    # Read-only mode

    async def enable_read_only(self) -> None:
        from sqlalchemy import event

        if self.engine is None:
            raise RuntimeError("read_only needs an engine; set sqlalchemy.engine.")
        dialect = self.sync_engine.dialect.name
        if dialect == "postgresql":
            # Every transaction starts with BEGIN READ ONLY. Unlike a session-level
            # SET, this survives transaction poolers such as PgBouncer, Neon and
            # Supabase, where each transaction may run on a different server connection.
            def on_checkout(connection: Any) -> None:
                connection.execution_options(postgresql_readonly=True)

            target, name, listener = self.sync_engine, "engine_connect", on_checkout
        elif dialect == "sqlite":

            def on_connect(dbapi_connection: Any, connection_record: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA query_only = ON")
                cursor.close()

            target, name, listener = self.sync_engine, "connect", on_connect
        else:
            raise NotImplementedError(
                f"read_only is not supported for {dialect} databases. "
                "Connect with a read-only database user instead."
            )

        event.listen(target, name, listener)
        self._listeners.append((target, name, listener))
        self.read_only = True
        # Pooled connections were opened before the listener existed.
        await self._dispose()

    # Recovering from errors

    def on_error(self, error: BaseException) -> None:
        from sqlalchemy.exc import DBAPIError, SQLAlchemyError

        session = self.session
        if session is None or not _caused_by(error, SQLAlchemyError):
            return
        sync_session = getattr(session, "sync_session", session)
        if not sync_session.in_transaction():
            return
        # After a failed flush the session refuses to continue, and after any
        # database error PostgreSQL rejects every statement until a rollback.
        aborted = self.sync_engine is not None and (
            self.sync_engine.dialect.name == "postgresql" and _caused_by(error, DBAPIError)
        )
        if sync_session.is_active and not aborted:
            return
        self.context.runtime.resolve(session.rollback())
        self.context.console.print(
            f"[dim]note: {self.options.session_name} was rolled back after the error; "
            "uncommitted changes were discarded.[/]"
        )

    # Teardown

    async def _dispose(self) -> None:
        result = self.engine.dispose()
        if hasattr(result, "__await__"):
            await result

    async def teardown(self) -> None:
        from sqlalchemy import event

        for target, name, fn in self._listeners:
            if event.contains(target, name, fn):
                event.remove(target, name, fn)
        self._listeners.clear()

        if self.session is not None:
            result = self.session.close()
            if hasattr(result, "__await__"):
                await result
            self.session = None
        # Read-only connections must not outlive the shell in a shared pool.
        if self.engine is not None and (self.options.dispose_engine or self.read_only):
            await self._dispose()

    def tip(self, namespace: dict[str, Any]) -> str | None:
        session_name = self.options.session_name
        if session_name not in namespace:
            return None
        model = next(
            (e for e, v in namespace.items() if isinstance(v, type) and _is_mapped(v)), None
        )
        target = f"select({model}).limit(5)" if model else "text('select 1')"
        if self.is_async:
            return (
                f"(await {session_name}.scalars({target})).all()"
                if model
                else (f"await {session_name}.scalar({target})")
            )
        return (
            f"{session_name}.scalars({target}).all()"
            if model
            else (f"{session_name}.scalar({target})")
        )


def _caused_by(error: BaseException, kind: type[BaseException]) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, kind):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def _is_live(cls: type) -> bool:
    """False for classes whose module has been unloaded (stale registry entries)."""
    return cls.__module__ in sys.modules


def _is_mapped(cls: type) -> bool:
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.orm import Mapper

    return isinstance(sa_inspect(cls, raiseerr=False), Mapper)
