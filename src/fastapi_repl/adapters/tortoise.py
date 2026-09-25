"""Tortoise ORM adapter."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from typing import Any

from fastapi_repl.adapters.base import ModelInfo, ORMAdapter, iter_classes, mask_url
from fastapi_repl.imports import import_string
from fastapi_repl.sql import SQLPrinter

_SQL_LOGGER = "tortoise.db_client"


class _SQLHandler(logging.Handler):
    def __init__(self, printer: SQLPrinter) -> None:
        super().__init__(level=logging.DEBUG)
        self.printer = printer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover
            return
        statement, params = message, None
        if ": [" in message and message.endswith("]"):
            statement, _, rest = message.rpartition(": [")
            params = "[" + rest
        self.printer(statement, params)


class TortoiseAdapter(ORMAdapter):
    """Initialises Tortoise ORM and loads its models.

    If Tortoise is already initialised (for example by ``RegisterTortoise`` in
    your app's lifespan with ``lifespan = true``), it is used as is. Otherwise
    the adapter calls ``Tortoise.init`` with ``tortoise.config``,
    ``tortoise.config_file`` or ``tortoise.db_url`` + ``tortoise.modules``, and
    closes the connections on exit.
    """

    name = "tortoise"
    display_name = "Tortoise ORM"
    package = "tortoise"

    def __init__(self, context: Any) -> None:
        super().__init__(context)
        self.initialised_here = False
        self._handler: _SQLHandler | None = None
        self._logger_state: tuple[int, bool] | None = None
        self._url: str | None = context.config.tortoise.db_url

    @classmethod
    def detect(cls, context: Any) -> bool:
        options = context.config.tortoise
        if options.config or options.config_file or options.db_url:
            return True
        if "tortoise" not in sys.modules:
            return False
        if cls.is_ready():
            return True
        from tortoise.models import Model

        return any(issubclass(c, Model) and c is not Model for c in iter_classes(context.modules))

    @property
    def options(self) -> Any:
        return self.config.tortoise

    def database(self) -> str | None:
        return mask_url(self._url) if self._url else None

    @staticmethod
    def is_ready() -> bool:
        from tortoise import Tortoise

        checker = getattr(Tortoise, "is_inited", None)
        if callable(checker):
            return bool(checker())
        return bool(getattr(Tortoise, "_inited", False))

    async def setup(self) -> None:
        from tortoise import Tortoise

        if self.is_ready():
            return
        opts = self.options
        kwargs: dict[str, Any] = {}
        if opts.config:
            config = import_string(opts.config)
            config = config() if callable(config) else config
            kwargs["config"] = config
            connections = config.get("connections", {}) if isinstance(config, dict) else {}
            urls = [c for c in connections.values() if isinstance(c, str)]
            self._url = urls[0] if len(urls) == 1 else None
        elif opts.config_file:
            kwargs["config_file"] = str((self.context.root / opts.config_file).resolve())
        elif opts.db_url:
            if not opts.modules:
                raise ValueError("tortoise.db_url needs tortoise.modules, e.g. {models = [...]}.")
            kwargs["db_url"] = opts.db_url
            kwargs["modules"] = opts.modules
        else:
            return
        await Tortoise.init(**kwargs)
        self.initialised_here = True
        if opts.generate_schemas:
            await Tortoise.generate_schemas(safe=True)

    def discover_models(self) -> Iterable[ModelInfo]:
        from tortoise import Tortoise

        apps = Tortoise.apps if self.is_ready() else None
        if apps:
            for label, models in apps.items():
                for model in models.values():
                    yield ModelInfo.from_class(model, self.name, label=label)
            return
        from tortoise.models import Model

        for cls in iter_classes(self.context.modules):
            if issubclass(cls, Model) and cls is not Model:
                if getattr(getattr(cls, "_meta", None), "abstract", False):
                    continue
                yield ModelInfo.from_class(cls, self.name)

    def default_imports(self) -> list[str]:
        return [
            "from tortoise import Tortoise, connections",
            "from tortoise.expressions import Q, F",
            "from tortoise.functions import Count, Sum, Avg, Max, Min",
            "from tortoise.transactions import in_transaction",
        ]

    def enable_sql_echo(self, printer: SQLPrinter) -> None:
        logger = logging.getLogger(_SQL_LOGGER)
        self._logger_state = (logger.level, logger.propagate)
        self._handler = _SQLHandler(printer)
        logger.addHandler(self._handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

    async def teardown(self) -> None:
        if self._handler is not None:
            logger = logging.getLogger(_SQL_LOGGER)
            logger.removeHandler(self._handler)
            if self._logger_state is not None:
                logger.setLevel(self._logger_state[0])
                logger.propagate = self._logger_state[1]
            self._handler = None
        if self.initialised_here:
            from tortoise import Tortoise

            await Tortoise.close_connections()
            self.initialised_here = False
            try:
                from tortoise.context import _current_context
            except ImportError:  # Tortoise < 1.0 keeps global state
                return
            _current_context.set(None)

    def tip(self, namespace: dict[str, Any]) -> str | None:
        from tortoise.models import Model

        model = next(
            (
                n
                for n, v in namespace.items()
                if isinstance(v, type) and issubclass(v, Model) and v is not Model
            ),
            None,
        )
        return f"await {model}.all().limit(5)" if model else None
