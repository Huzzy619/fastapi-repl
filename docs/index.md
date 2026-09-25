# fastapi-repl

**Django's `shell_plus`, for FastAPI and every other ASGI framework.**

fastapi-repl opens an interactive Python shell with your project already loaded: every
model, your database engine and a ready-to-use session, the helpers you always import,
and anything else you ask for. Top-level `await` works in every supported shell, on a
single event loop that owns your async connection pool.

```console
$ fastapi-repl
In [1]: await session.scalar(select(func.count(User.id)))
Out[1]: 1284
```

## Why

FastAPI deliberately has no management commands, so there is no `manage.py shell`.
Most teams end up with a `scripts/shell.py` that imports a few things and calls
`asyncio.run()` on every query. It breaks with async drivers, forgets new models and
is copied from project to project. fastapi-repl is that script, done properly.

## Highlights

- **ORM agnostic.** Built-in adapters for [SQLAlchemy](guides/sqlalchemy.md) (sync and
  async), [SQLModel](guides/sqlmodel.md) and [Tortoise ORM](guides/tortoise.md), plus a
  [small plugin API](guides/writing-adapters.md) for anything else.
- **Top-level `await`** in [IPython, ptpython, ptipython and plain Python](guides/interfaces.md),
  all on [one shared event loop](guides/async.md).
- **Auto-imports**: models, ORM helpers, your own imports and objects, with
  [collision handling](configuration.md#collision) and aliases.
- **Runs your app's lifespan** on request, so startup code is live in the shell.
- **Everything shell_plus does**: `--print-sql`, `-c`, stdin, scripts, Jupyter,
  `dont_load`, pre/post imports and more. See [Migrating from Django](migrating-from-django.md).
- **Great ergonomics**: `init` writes your config, `config` shows where each value came
  from, `doctor` finds problems, `imports` lists every name.

## Where next

<div class="grid cards" markdown>

- [**Getting started**](getting-started.md): install, configure and run your first query.
- [**Configuration**](configuration.md): every setting, with env vars and flags.
- [**CLI reference**](cli.md): every command and option.
- [**Recipes**](recipes.md): common setups and tricks.

</div>

!!! note
    fastapi-repl is an independent project and is not affiliated with FastAPI.
