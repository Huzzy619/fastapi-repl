# SQLAlchemy

The SQLAlchemy adapter supports SQLAlchemy 2.x with both sync and async engines.

## Typical async setup

Given a project like this:

```python title="app/db.py"
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

engine = create_async_engine("postgresql+asyncpg://localhost/app")
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass
```

the config is:

```toml
[tool.fastapi-repl]
models = ["app.models"]
base = "app.db:Base"

[tool.fastapi-repl.sqlalchemy]
engine = "app.db:engine"
session_factory = "app.db:SessionLocal"
```

and in the shell:

<!-- test: sa_async -->
```python
# Rows
users = (await session.scalars(select(User).order_by(User.name))).all()

# Eager loading
post = (await session.scalars(select(Post).options(selectinload(Post.author)))).first()
print(post.author.name)

# Aggregates
await session.scalar(select(func.count()).select_from(User))

# Writes
session.add(User(name="linus"))
await session.commit()
```

## Sync setup

Sync engines work the same way; `session` is a regular `Session`:

```python
session.scalars(select(User).limit(5)).all()
session.get(User, 1)
```

## What gets loaded

| Name                       | What it is                                                     |
| -------------------------- | -------------------------------------------------------------- |
| Every mapped model         | From `base`'s registry and every mapped class in `models`.    |
| `engine`                   | From `sqlalchemy.engine`, or auto-detected.                    |
| `session`                  | An `AsyncSession` or `Session`, closed on exit.                |
| `select`, `insert`, `update`, `delete`, `func`, `text` | Core constructs.                   |
| `and_`, `or_`, `not_`, `desc`, `asc`, `case`, `cast`, `literal`, `exists` | Expression helpers. |
| `sa_inspect`               | `sqlalchemy.inspect`, renamed so it does not shadow the stdlib. |
| `selectinload`, `joinedload`, `load_only`, `aliased` | ORM loading helpers.                |
| `AsyncSession` or `Session` | The session class.                                            |

Turn the helpers off with `default_imports = false` or `--no-helpers`.

## How models are found

1. Each class in `base` contributes its whole registry.
2. Each module in `models` (recursively for packages) is scanned for mapped classes,
   and their registries are included too. This catches models on other bases.
3. If neither is configured, every registry SQLAlchemy knows about is used. This works
   whenever the app (or anything else) has already imported the models.

Only classes whose module is still imported are loaded, and abstract classes are skipped
because they are not mapped.

## The engine

If `sqlalchemy.engine` is not set, fastapi-repl looks for engines in memory after your
code is imported. If there is exactly one `AsyncEngine` or `Engine`, it is used. If
there are several, you get a warning asking you to pick one.

On exit the engine's pool is disposed (turn this off with `dispose_engine = false`).
This matters for async drivers such as asyncpg, which otherwise complain about
connections being garbage collected after the loop closed.

## Sessions

- With `session_factory`, the factory is called with no arguments, so any options you
  set on your `sessionmaker` (such as `expire_on_commit=False`) apply.
- Without it, `AsyncSession(engine, expire_on_commit=False)` or `Session(engine)` is
  created.
- Rename it with `session_name = "db"`, or turn it off with `session = false`.
- Defining your own `session` in `objects` also turns off the built-in one.

!!! warning "Transactions"
    The shell session behaves like any other: changes are only saved when you call
    `commit()`, and a failed statement leaves the session needing a `rollback()`.

## Printing SQL

```console
$ fastapi-repl --print-sql
```

Every statement, its parameters and its duration are printed to stderr. Add
`--truncate-sql 300` for long statements, and `--print-sql-location` (sync engines only)
to see which line ran each query.
