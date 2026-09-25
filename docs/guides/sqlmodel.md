# SQLModel

The SQLModel adapter builds on the [SQLAlchemy adapter](sqlalchemy.md), so everything on
that page applies. The differences:

- It is chosen automatically when your project imports `sqlmodel`, and it replaces the
  plain SQLAlchemy adapter.
- Table models (`table=True`) are found through SQLModel's default registry, so they
  are loaded as soon as they are imported. Data-only models such as `HeroRead` are not.
- `session` is a `sqlmodel.Session` (or `sqlmodel.ext.asyncio.session.AsyncSession`),
  so `session.exec()` works.
- `select` is SQLModel's version, and `SQLModel`, `Field`, `Relationship` and `col` are
  imported too.

## Minimal setup

If you use FastAPI CLI, you may not need any config: with `[tool.fastapi] entrypoint`
set, the app is imported, which imports your models, and the engine is auto-detected.

```toml
[tool.fastapi]
entrypoint = "app.main:app"
```

Otherwise point fastapi-repl at your models and engine:

```toml
[tool.fastapi-repl]
models = ["app.models"]

[tool.fastapi-repl.sqlalchemy]
engine = "app.db:engine"
```

## In the shell

<!-- test: sqlmodel_proj -->
```python
heroes = session.exec(select(Hero).where(Hero.power > 5)).all()
hero = session.get(Hero, 1)
session.add(Hero(name="Spider-Boy", power=4))
session.commit()
```

With an async engine:

```python
heroes = (await session.exec(select(Hero))).all()
```
