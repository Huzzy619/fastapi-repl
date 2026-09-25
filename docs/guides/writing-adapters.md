# Writing an adapter

An adapter teaches fastapi-repl about an ORM (or any library with "models" and a
connection: an ODM, a search client, a key-value store). It is a small class; every
method has a default, so you only write the parts you need.

## A complete example

This adapter supports a made-up ORM. It is the adapter used in fastapi-repl's own
test suite.

```python title="my_orm_repl/adapter.py"
from fastapi_repl import ModelInfo, ORMAdapter

from my_orm import Database, Model


class MyORMAdapter(ORMAdapter):
    name = "myorm"  # used in `adapters = [...]` and plugin options
    display_name = "My ORM"  # shown in the banner
    package = "my_orm"  # import name; used by the default detect()

    async def setup(self) -> None:
        url = self.context.options.get("url", "memory://")
        self.db = await Database.connect(url)

    def discover_models(self):
        for cls in Model.registry:
            yield ModelInfo.from_class(cls, self.name)

    def default_imports(self) -> list[str]:
        return ["from my_orm import Q, fn"]

    def objects(self) -> dict:
        return {"db": self.db}

    def enable_sql_echo(self, printer) -> None:
        self.db.on_query(lambda sql, params: printer(sql, params))

    async def teardown(self) -> None:
        await self.db.close()

    def tip(self, namespace: dict) -> str | None:
        return "await db.fetch('select 1')"
```

## Registering it

**As an installable plugin**, add an entry point in the plugin's `pyproject.toml`:

```toml
[project.entry-points."fastapi_repl.adapters"]
myorm = "my_orm_repl.adapter:MyORMAdapter"
```

Once installed, it takes part in auto-detection like the built-in adapters.

**Inside a single project**, list the import path in the config. This also turns off
auto-detection, so list every adapter you want:

```toml
[tool.fastapi-repl]
adapters = ["app.shell:MyORMAdapter", "sqlalchemy"]
```

**Options** for your adapter live in `[tool.fastapi-repl.plugins.<name>]` and arrive as
the `self.context.options` dict:

```toml
[tool.fastapi-repl.plugins.myorm]
url = "postgres://localhost/app"
```

## Lifecycle

For each shell session, fastapi-repl:

1. Imports `pre_imports`, the `app`, `models` and `base`, and runs the lifespan if enabled.
2. Calls the class method `detect(context)` on every installed adapter (only when the
   `adapters` setting is empty). An adapter's `replaces` tuple removes other adapters it
   supersedes; SQLModel's adapter sets `replaces = ("sqlalchemy",)`.
3. Creates the adapter with an `AdapterContext` and awaits `setup()`, then awaits
   `enable_read_only()` if `read_only` is on.
4. Collects `default_imports()`, `discover_models()` and `objects()`.
5. Runs startup hooks, then calls `enable_sql_echo(printer)` if `--print-sql` is on.
6. While the shell is open, calls `on_error(error)` after each failed statement (if
   `rollback_on_error` is on).
7. On exit, awaits `teardown()`.

All async methods run on the session's single event loop, the same one the user's code
runs on. Objects you create in `setup()` can safely hold connections.

## Reference

### Class attributes

| Attribute      | Purpose                                                              |
| -------------- | -------------------------------------------------------------------- |
| `name`         | Unique identifier. Required.                                         |
| `display_name` | Name in the banner. Defaults to `name`.                              |
| `package`      | Import name of the ORM. Used by `is_installed()`, `detect()` and `version()`. |
| `replaces`     | Names of adapters this one makes redundant.                          |

### Methods

| Method                          | Default                               | Notes                                          |
| ------------------------------- | ------------------------------------- | ---------------------------------------------- |
| `detect(context)` (classmethod) | `package in sys.modules`              | Called after the project is imported. Prefer real evidence (models exist, a config is set) over "the package is installed". |
| `async setup()`                 | nothing                               | Connect, initialise, read `context.options`.   |
| `async enable_read_only()`      | raises                                | Make connections read-only, or raise. Raising stops the shell from starting, so never pretend. |
| `database()`                    | `None`                                | Where you are connected, for the banner. Use `mask_url()` from `fastapi_repl.adapters.base` to hide passwords. |
| `on_error(error)`               | nothing                               | Recover after a failed statement, e.g. roll back a broken session. Runs outside the event loop; use `context.runtime.run()` for async work. |
| `discover_models()`             | nothing                               | Yield `ModelInfo`s. Use `ModelInfo.from_class(cls, self.name, label=...)`. |
| `default_imports()`             | `[]`                                  | [Import specs](../configuration.md#import-specs). Skipped with `--no-helpers`. |
| `objects()`                     | `{}`                                  | Name to value. User `objects` with the same name win. |
| `enable_sql_echo(printer)`      | nothing                               | Call `printer(statement, params=None, duration=None, many=False, caller=None)` for each statement. |
| `async teardown()`              | nothing                               | Close what `setup()` opened.                   |
| `tip(namespace)`                | `None`                                | One line of example code for the banner.       |
| `describe()`                    | `"<display_name> <version>"`          | Banner summary.                                |

### `AdapterContext`

| Field      | What it holds                                                     |
| ---------- | ----------------------------------------------------------------- |
| `config`   | The resolved `ReplConfig`.                                        |
| `runtime`  | The session `Runtime`. `runtime.run(coro)` runs a coroutine on the loop. |
| `console`  | A Rich console for output.                                        |
| `root`     | The project root.                                                 |
| `modules`  | Modules imported from `models`, including submodules.             |
| `bases`    | Objects imported from `base`.                                     |
| `app`      | The ASGI app, or `None`.                                          |
| `options`  | This adapter's plugin options.                                    |
| `warn`     | Call with a message to report a non-fatal problem.                |

`iter_classes(modules)` from `fastapi_repl.adapters.base` yields each class in a list
of modules once, which is handy for scanning `context.modules`.

## Testing your adapter

Use `build_namespace()` to exercise the whole pipeline without starting a shell:

```python
from fastapi_repl import build_namespace


def test_models_are_loaded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session, ns = build_namespace(adapters=["my_orm_repl.adapter:MyORMAdapter"])
    try:
        assert "db" in ns
    finally:
        session.close()
```
