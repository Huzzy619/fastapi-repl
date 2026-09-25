"""ORM adapters and adapter discovery.

Built-in adapters are always available. Third-party adapters are found through
the ``fastapi_repl.adapters`` entry point group, and project-local adapters
can be listed by import path in the ``adapters`` setting.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from fastapi_repl.adapters.base import AdapterContext, ModelInfo, ORMAdapter
from fastapi_repl.errors import ConfigError
from fastapi_repl.imports import import_string

ENTRY_POINT_GROUP = "fastapi_repl.adapters"

BUILTIN_ADAPTERS: dict[str, str] = {
    "sqlalchemy": "fastapi_repl.adapters.sqlalchemy:SQLAlchemyAdapter",
    "sqlmodel": "fastapi_repl.adapters.sqlmodel:SQLModelAdapter",
    "tortoise": "fastapi_repl.adapters.tortoise:TortoiseAdapter",
}

__all__ = [
    "BUILTIN_ADAPTERS",
    "ENTRY_POINT_GROUP",
    "AdapterContext",
    "ModelInfo",
    "ORMAdapter",
    "available_adapters",
    "load_adapter_class",
    "select_adapters",
]


def available_adapters() -> dict[str, str]:
    """Map adapter names to import paths: built-ins plus installed plugins.

    A plugin registered under the same name as a built-in replaces it.
    """
    found = dict(BUILTIN_ADAPTERS)
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        found[ep.name] = ep.value
    return found


def load_adapter_class(name_or_path: str) -> type[ORMAdapter]:
    """Load an adapter class by registered name or ``module:Class`` path."""
    path = available_adapters().get(name_or_path, name_or_path)
    if ":" not in path and "." not in path:
        known = ", ".join(sorted(available_adapters()))
        raise ConfigError(f"Unknown adapter '{name_or_path}'. Known adapters: {known}.")
    cls = import_string(path)
    if not (isinstance(cls, type) and issubclass(cls, ORMAdapter)):
        raise ConfigError(f"'{path}' is not an ORMAdapter subclass.")
    return cls


def select_adapters(context: AdapterContext) -> list[ORMAdapter]:
    """Instantiate the adapters for this session.

    With an explicit ``adapters`` list, exactly those are used. Otherwise each
    installed adapter's ``detect()`` is asked, and adapters listed in another
    detected adapter's ``replaces`` are dropped.
    """
    config = context.config
    classes: list[type[ORMAdapter]] = []
    if config.adapters:
        classes = [load_adapter_class(name) for name in config.adapters]
    else:
        for name, path in available_adapters().items():
            try:
                cls = load_adapter_class(path)
            except Exception as exc:
                context.warn(f"Could not load adapter '{name}': {exc}")
                continue
            if not cls.is_installed():
                continue
            try:
                if cls.detect(context):
                    classes.append(cls)
            except Exception as exc:
                context.warn(f"Adapter '{name}' failed to detect: {exc}")
        replaced = {r for cls in classes for r in cls.replaces}
        classes = [cls for cls in classes if cls.name not in replaced]

    adapters: list[ORMAdapter] = []
    for cls in classes:
        adapter_context = AdapterContext(
            config=context.config,
            runtime=context.runtime,
            console=context.console,
            root=context.root,
            modules=context.modules,
            bases=context.bases,
            app=context.app,
            options=dict(config.plugins.get(cls.name, {})),
            warn=context.warn,
        )
        adapters.append(cls(adapter_context))
    return adapters
