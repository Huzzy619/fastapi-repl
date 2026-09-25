# fastapi-repl

**Django's `shell_plus`, for FastAPI.** One command opens an interactive shell with your
models, database engine, session and favourite imports already loaded, and top-level
`await` that just works with async drivers.

```console
$ fastapi-repl
╭──────────────────────────────────────────────────────────────────────────────────╮
│ fastapi-repl 0.1.0  Python 3.12.11 · IPython 9.5.0 · SQLAlchemy 2.0.54 (async)   │
│ Project: /home/me/code/my-api                                                    │
│                                                                                  │
│ ORM helpers  select, insert, update, delete, func, text, and_, or_, not_, desc,  │
│              asc, case, cast, literal, exists, selectinload, joinedload, ...     │
│ Models (12)  User, Account, Post, Comment, Tag, Subscription, ...                │
│ Objects      app (FastAPI), engine (AsyncEngine), session (AsyncSession)         │
│ Imports      settings                                                            │
│                                                                                  │
│ Top-level await is on, try: (await session.scalars(select(User).limit(5))).all() │
╰──────────────────────────────────────────────────────────────────────────────────╯

In [1]: user = await session.scalar(select(User).where(User.email == "ada@example.com"))
```

FastAPI has no built-in shell, so every project ends up with a half-working
`python -i` script. fastapi-repl replaces that script with something you can configure and
reuse across projects.

- **ORM agnostic.** SQLAlchemy (sync and async), SQLModel and Tortoise ORM work out of the
  box. Any other ORM can be supported with a small adapter class.
- **Top-level `await`** in IPython, ptpython, ptipython and the plain Python shell, all
  running on one shared event loop so async connection pools keep working between lines.
- **Auto-imports** every model, plus helpers like `select`, `func`, `selectinload` or
  `Q`, `F`, `Count`, plus anything you add. Name collisions are handled for you.
- **Your app, started.** Optionally runs your ASGI lifespan so startup code (connection
  pools, caches, Tortoise's `RegisterTortoise`...) is live in the shell.
- **Everything `shell_plus` does:** `--print-sql`, `-c`, piped stdin, scripts, Jupyter
  notebooks, `--dont-load`, model aliases, pre/post imports, `PYTHONSTARTUP`...
- **Works with any ASGI framework**: FastAPI, Starlette, Litestar, or no framework at all.
- **Configured in `pyproject.toml`**, overridable by environment variables and flags,
  with `fastapi-repl config` showing where each value came from.

> fastapi-repl is an independent project and is not affiliated with FastAPI.

## Install

```console
pip install "fastapi-repl[ipython]"      # or: uv add --dev "fastapi-repl[ipython]"
```

The extras are optional: `ipython`, `ptpython`, `bpython`, `jupyter`, or `all`. Without
any of them you get the plain Python shell, still with top-level `await`. Python 3.11+ is
required.

## Quick start

```console
$ fastapi-repl init        # detects your app, models, engine and session factory
$ fastapi-repl             # start the shell
```

`init` writes a config like this to `pyproject.toml`. You can also write it by hand:

```toml
[tool.fastapi-repl]
models = ["app.models"]
base = "app.db:Base"
env_file = ".env"
imports = ["from app.core.config import settings"]

[tool.fastapi-repl.sqlalchemy]
engine = "app.db:engine"
session_factory = "app.db:SessionLocal"
```

Then:

```console
$ fastapi-repl --ptpython               # pick an interface
$ fastapi-repl --print-sql              # print every SQL statement
$ fastapi-repl -c "print(await session.scalar(select(func.count(User.id))))"
$ fastapi-repl run scripts/backfill.py  # run a script with everything loaded
$ fastapi-repl --lab                    # JupyterLab with a preloaded kernel
$ fastapi-repl imports                  # what gets loaded, and from where
$ fastapi-repl doctor                   # diagnose problems
```

## Coming from Django?

| Django / django-extensions                | fastapi-repl                           |
| ----------------------------------------- | -------------------------------------- |
| `manage.py shell_plus`                    | `fastapi-repl`                         |
| `shell_plus --ipython` / `--ptpython`     | `fastapi-repl --ipython` / `--ptpython`|
| `shell_plus --print-sql`                  | `fastapi-repl --print-sql`             |
| `shell -c "..."`                          | `fastapi-repl -c "..."` (with `await`) |
| `shell_plus --notebook` / `--lab`         | `fastapi-repl --notebook` / `--lab`    |
| `runscript`                               | `fastapi-repl run`                     |
| `SHELL_PLUS_PRE_IMPORTS`                  | `pre_imports`                          |
| `SHELL_PLUS_MODEL_ALIASES`                | `model_aliases`                        |
| `SHELL_PLUS_DONT_LOAD`                    | `dont_load`                            |

See the full [migration guide](docs/migrating-from-django.md).

## Documentation

- [Getting started](docs/getting-started.md)
- [Configuration reference](docs/configuration.md)
- [CLI reference](docs/cli.md)
- Guides: [SQLAlchemy](docs/guides/sqlalchemy.md), [SQLModel](docs/guides/sqlmodel.md),
  [Tortoise ORM](docs/guides/tortoise.md), [async and the event loop](docs/guides/async.md),
  [interfaces](docs/guides/interfaces.md), [writing an adapter](docs/guides/writing-adapters.md)
- [Recipes](docs/recipes.md), [security](docs/security.md),
  [troubleshooting](docs/troubleshooting.md), [FAQ](docs/faq.md)

## Contributing

Bug reports and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get a
development environment running in a minute.

## License

[MIT](LICENSE)
