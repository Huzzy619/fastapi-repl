# Getting started

This page takes you from nothing to running queries in about five minutes.

## 1. Install

fastapi-repl is a development tool, so add it as a dev dependency:

=== "uv"

    ```console
    uv add --dev "fastapi-repl[ipython]"
    ```

=== "pip"

    ```console
    pip install "fastapi-repl[ipython]"
    ```

=== "Poetry"

    ```console
    poetry add --group dev "fastapi-repl[ipython]"
    ```

The `[ipython]` extra installs IPython, the recommended interface. Other extras are
`ptpython`, `bpython`, `jupyter` and `all`. With no extras you still get a plain Python
shell with top-level `await` and tab completion.

fastapi-repl needs Python 3.11 or newer.

## 2. Generate a config

From anywhere inside your project:

```console
$ fastapi-repl init
Project: /home/me/code/my-api
  ✓ ORM: sqlalchemy
  ✓ App: app.main:app
  ✓ Models: app.models
  ✓ Base: app.db.base:Base
  ✓ Engine: app.db.session:engine
  ✓ Session factory: app.db.session:SessionLocal
  ✓ .env: .env

Wrote config to /home/me/code/my-api/pyproject.toml. Start the shell with fastapi-repl.
```

`init` reads your source files (it never imports them) and appends a
`[tool.fastapi-repl]` table to `pyproject.toml`:

```toml
[tool.fastapi-repl]
app = "app.main:app"
env_file = ".env"
models = ["app.models"]
base = "app.db.base:Base"
# Extra names, e.g. "from app.core.config import settings"
imports = []

[tool.fastapi-repl.sqlalchemy]
engine = "app.db.session:engine"
session_factory = "app.db.session:SessionLocal"
```

Prefer a separate file? Run `fastapi-repl init --standalone` to write
`fastapi-repl.toml` instead. Want to see the result first? Add `--dry-run`.

!!! tip "Zero config"
    Many projects work with no config at all. If `pyproject.toml` has FastAPI CLI's
    `[tool.fastapi] entrypoint`, fastapi-repl imports that app, and every model the app
    imports is discovered through the ORM's registry.

## 3. Start the shell

```console
$ fastapi-repl
```

The banner lists everything that was loaded. Try the suggested line at the bottom, or
write your own:

```python
users = (await session.scalars(select(User).order_by(User.created_at.desc()).limit(5))).all()
users[0].email
```

`session` is an `AsyncSession` for async engines and a `Session` for sync ones. It is
closed for you when you exit.

## 4. Make it yours

Add the things you always import:

```toml
[tool.fastapi-repl]
imports = [
  "from app.core.config import settings",
  "from app.services import billing",
  "import datetime as dt",
]

[tool.fastapi-repl.objects]
redis = "app.cache:get_redis()"   # "()" calls the factory
```

Then check what the shell will contain, and where each name comes from:

```console
$ fastapi-repl imports
```

## 5. Everyday commands

| Command                                   | What it does                                 |
| ----------------------------------------- | -------------------------------------------- |
| `fastapi-repl`                            | Start the shell (IPython if installed).      |
| `fastapi-repl --ptpython`                 | Use a different interface.                   |
| `fastapi-repl --print-sql`                | Print every SQL statement as it runs.        |
| `fastapi-repl --lifespan`                 | Run your app's startup/shutdown code.        |
| `fastapi-repl -c "..."`                   | Run code and exit (`await` works).           |
| `fastapi-repl run scripts/seed.py`        | Run a script with everything preloaded.      |
| `fastapi-repl --lab`                      | Open JupyterLab with a preloaded kernel.     |
| `fastapi-repl config`                     | Show the resolved config and its sources.    |
| `fastapi-repl doctor`                     | Diagnose setup problems.                     |

## Next steps

- Read the guide for your ORM: [SQLAlchemy](guides/sqlalchemy.md),
  [SQLModel](guides/sqlmodel.md) or [Tortoise ORM](guides/tortoise.md).
- Browse the [configuration reference](configuration.md).
- Learn [how `await` works](guides/async.md) in the shell.
