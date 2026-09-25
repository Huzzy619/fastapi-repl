"""SQLModel adapter. Builds on the SQLAlchemy adapter."""

from __future__ import annotations

import sys
from typing import Any

from fastapi_repl.adapters.base import iter_classes
from fastapi_repl.adapters.sqlalchemy import SQLAlchemyAdapter


class SQLModelAdapter(SQLAlchemyAdapter):
    """Like the SQLAlchemy adapter, but with SQLModel's session classes and helpers.

    Table models (``table=True``) are found through SQLModel's default
    registry, so ``models`` and ``base`` are optional once your models are
    imported (for example by importing the app).
    """

    name = "sqlmodel"
    display_name = "SQLModel"
    package = "sqlmodel"
    replaces = ("sqlalchemy",)

    @classmethod
    def detect(cls, context: Any) -> bool:
        if "sqlmodel" not in sys.modules:
            return False
        from sqlmodel import SQLModel
        from sqlmodel.main import default_registry

        if any(isinstance(b, type) and issubclass(b, SQLModel) for b in context.bases):
            return True
        if any(
            issubclass(c, SQLModel) and hasattr(c, "__table__")
            for c in iter_classes(context.modules)
        ):
            return True
        return any(m.class_.__module__ in sys.modules for m in default_registry.mappers)

    def registries(self) -> list[Any]:
        registries = super().registries()
        try:
            from sqlmodel.main import default_registry
        except ImportError:  # pragma: no cover
            return registries
        if all(r is not default_registry for r in registries):
            registries.append(default_registry)
        return registries

    def make_session(self) -> Any:
        if self.options.session_factory or self.engine is None:
            return super().make_session()
        if self.is_async:
            from sqlmodel.ext.asyncio.session import AsyncSession

            return AsyncSession(self.engine, expire_on_commit=False)
        from sqlmodel import Session

        return Session(self.engine)

    def default_imports(self) -> list[str]:
        imports = [
            spec
            for spec in super().default_imports()
            if not spec.endswith(("import AsyncSession", "import Session"))
        ]
        imports.append("from sqlmodel import SQLModel, Field, Relationship, select, col")
        if self.is_async:
            imports.append("from sqlmodel.ext.asyncio.session import AsyncSession")
        else:
            imports.append("from sqlmodel import Session")
        return imports

    def tip(self, namespace: dict[str, Any]) -> str | None:
        session_name = self.options.session_name
        if session_name not in namespace:
            return None
        model = next(
            (
                n
                for n, v in namespace.items()
                if isinstance(v, type)
                and getattr(v, "__tablename__", None)
                and hasattr(v, "model_fields")
            ),
            None,
        )
        if model is None:
            return super().tip(namespace)
        if self.is_async:
            return f"(await {session_name}.exec(select({model}).limit(5))).all()"
        return f"{session_name}.exec(select({model}).limit(5)).all()"
