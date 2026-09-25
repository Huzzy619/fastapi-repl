# Configuration reference

## Where settings come from

fastapi-repl merges settings from these sources. Later sources win:

1. Built-in defaults.
2. The `[tool.fastapi-repl]` table in `pyproject.toml`.
3. A standalone `fastapi-repl.toml` file (same keys, without the `[tool.fastapi-repl]` prefix).
4. Environment variables named `FASTAPI_REPL_<SETTING>`, including ones set in `env_file`.
5. Command-line flags.

Run `fastapi-repl config` to see the final values and where each one came from, or
`fastapi-repl config --changed` to hide defaults.

### Finding the project

fastapi-repl walks up from the current directory and uses the first directory that
contains a `fastapi-repl.toml`, or a `pyproject.toml` with a `[tool.fastapi-repl]` table.
If there is none, the nearest `pyproject.toml` wins, and failing that the current
directory. That directory is the **project root**: relative paths are resolved from it
and it is added to `sys.path`. Use `--config path/to/file.toml` to skip the search.

### Spelling

Keys can use dashes or underscores: `print-sql = true` and `print_sql = true` are the
same. Unknown keys are an error, so typos do not go unnoticed.

### Environment variables

Every setting has an environment variable: `FASTAPI_REPL_` followed by the setting name
in upper case. Nested settings use a double underscore.

```console
FASTAPI_REPL_PRINT_SQL=1
FASTAPI_REPL_MODELS=app.models,app.billing.models      # lists are comma separated
FASTAPI_REPL_SQLALCHEMY__ENGINE=app.db:engine          # [sqlalchemy] engine
FASTAPI_REPL_OBJECTS='{"redis": "app.cache:redis"}'    # tables are JSON
```

## Import specs

Several settings (`imports`, `pre_imports`, `post_imports`) take **import specs**:
strings that describe what to put in the shell. Three forms are accepted:

| Spec                                        | Result                                       |
| ------------------------------------------- | -------------------------------------------- |
| `"from app.core.config import settings"`    | Any Python import statement.                 |
| `"import datetime as dt; import json"`      | Several statements separated by `;`.         |
| `"from app.models import *"`                | Star imports respect `__all__`.              |
| `"app.core.config:settings"`                | Object path: binds `settings`.               |
| `"app.main:app.state"`                      | Attribute chains: binds `state`.             |
| `"app.db:get_session()"`                    | Calls the factory with no arguments.         |
| `"json"`                                    | Same as `"import json"`.                     |

**Object paths** (`module:attribute`) are also used by `objects`, `base`, `app`, hooks
and adapter options. Objects created with `()` are closed when the shell exits if they
have a `close()` or `aclose()` method. If the factory returns an awaitable, it is awaited.

**Generator factories**, such as FastAPI dependencies, work too:

```python title="app/db.py"
async def get_db():
    async with SessionLocal() as session:
        yield session
        await session.commit()
```

```toml
[tool.fastapi-repl.objects]
db = "app.db:get_db()"   # db is the yielded session
```

The shell gets the first value the generator yields. On exit the generator is closed,
which runs `with` exits and `finally` blocks but **not** the code after `yield`, so
leaving the shell never commits for you.

## Full example

```toml
[tool.fastapi-repl]
app = "app.main:app"
lifespan = false
env_file = ".env"
pythonpath = ["."]

interface = "auto"
interface_order = ["ipython", "ptpython", "bpython", "python"]

models = ["app.models"]
base = "app.db:Base"
dont_load = ["AuditLog", "app.models.legacy"]
collision = "prefix"

pre_imports = []
imports = [
  "from app.core.config import settings",
  "import datetime as dt",
]
post_imports = []

print_sql = false
read_only = false

[tool.fastapi-repl.model_aliases]
"app.billing.models.Account" = "BillingAccount"

[tool.fastapi-repl.objects]
redis = "app.cache:get_redis()"

[tool.fastapi-repl.hooks]
namespace = ["app.shell:extra_names"]
startup = []
shutdown = []

[tool.fastapi-repl.sqlalchemy]
engine = "app.db:engine"
session_factory = "app.db:SessionLocal"
```

## Project settings

### `app`

**Type:** string (object path) · **Default:** `[tool.fastapi] entrypoint`, if set ·
**Env:** `FASTAPI_REPL_APP` · **Flag:** `--app`

Your ASGI application, for example `"app.main:app"`. It is imported (so everything it
imports, such as routers and models, is loaded) and exposed in the shell as `app`. If
you use FastAPI CLI and have `[tool.fastapi] entrypoint` in `pyproject.toml`, that value
is used automatically.

### `lifespan`

**Type:** boolean · **Default:** `false` · **Env:** `FASTAPI_REPL_LIFESPAN` ·
**Flag:** `--lifespan / --no-lifespan`

Run the app's ASGI lifespan: startup before the shell opens, shutdown when it closes.
Use this when your app creates connection pools, HTTP clients or initialises an ORM
(like Tortoise's `RegisterTortoise`) at startup. The lifespan state (what a lifespan
function yields) is available as `lifespan_state`. Works with any ASGI 3 framework.

### `pythonpath`

**Type:** list of strings · **Default:** `["."]` · **Env:** `FASTAPI_REPL_PYTHONPATH`

Directories, relative to the project root, that are put on `sys.path`. Use `["src"]`
for a src layout.

### `env_file`

**Type:** string · **Default:** none · **Env:** `FASTAPI_REPL_ENV_FILE` ·
**Flag:** `--env-file`

A `.env` file loaded into the environment before any of your code is imported, so
settings classes find their variables. Existing environment variables are not
overwritten. The file can also contain `FASTAPI_REPL_*` variables.

## Interface settings

### `interface`

**Type:** `"auto"`, `"ipython"`, `"ptpython"`, `"ptipython"`, `"bpython"` or `"python"` ·
**Default:** `"auto"` · **Env:** `FASTAPI_REPL_INTERFACE` ·
**Flags:** `-i/--interface`, `--ipython`, `--ptpython`, `--ptipython`, `--bpython`, `--plain`

Which interactive shell to start. `auto` uses the first installed one from
`interface_order`. See [Interfaces](guides/interfaces.md).

### `interface_order`

**Type:** list of strings · **Default:** `["ipython", "ptpython", "bpython", "python"]` ·
**Env:** `FASTAPI_REPL_INTERFACE_ORDER`

Preference order for `interface = "auto"`. The plain Python shell is always the last
resort.

### `startup`

**Type:** boolean · **Default:** `true` · **Env:** `FASTAPI_REPL_STARTUP` ·
**Flag:** `--startup / --no-startup`

Run `$PYTHONSTARTUP` and `~/.pythonrc.py` in the plain Python shell, like Django's
`shell`. IPython and ptpython use their own startup files and config.

### `ipython_arguments`

**Type:** list of strings · **Default:** `[]` · **Env:** `FASTAPI_REPL_IPYTHON_ARGUMENTS` ·
**Flag:** `--ipython-arguments "..."`

Extra command-line arguments for IPython, for example `["--profile=work"]`.

### `jupyter_arguments`

**Type:** list of strings · **Default:** `[]` · **Env:** `FASTAPI_REPL_JUPYTER_ARGUMENTS` ·
**Flag:** `--jupyter-arguments "..."`

Extra command-line arguments for `jupyter notebook` / `jupyter lab`, for example
`["--no-browser", "--port=8899"]`.

## Model settings

### `adapters`

**Type:** list of strings · **Default:** `[]` (auto-detect) · **Env:** `FASTAPI_REPL_ADAPTERS`

ORM adapters to use, by name (`"sqlalchemy"`, `"sqlmodel"`, `"tortoise"`, or an
installed plugin) or import path (`"app.shell:MyAdapter"`). When empty, each installed
adapter checks whether your project uses its ORM. See
[Writing an adapter](guides/writing-adapters.md).

### `models`

**Type:** list of strings · **Default:** `[]` · **Env:** `FASTAPI_REPL_MODELS` ·
**Flag:** `-m/--models`

Modules or packages that contain your models. Packages are imported recursively, so
`"app.models"` also loads `app.models.billing`, `app.models.auth` and so on. Import
errors in a submodule are reported without stopping the shell.

This is optional when your models are imported anyway (by `app` or `base`), but listing
them guarantees nothing is missed.

### `base`

**Type:** list of strings (object paths) · **Default:** `[]` · **Env:** `FASTAPI_REPL_BASE`

Your declarative base class(es), for example `"app.db:Base"`. The SQLAlchemy adapter
loads every class mapped on the base's registry.

### `auto_imports`

**Type:** boolean · **Default:** `true` · **Env:** `FASTAPI_REPL_AUTO_IMPORTS` ·
**Flag:** `--no-imports`

Master switch. When false, nothing is imported automatically: you get an empty shell
with only the `await_` helper. Useful when your project fails to import.

### `load_models`

**Type:** boolean · **Default:** `true` · **Env:** `FASTAPI_REPL_LOAD_MODELS` ·
**Flag:** `--no-models`

Import discovered models into the shell.

### `dont_load`

**Type:** list of strings · **Default:** `[]` · **Env:** `FASTAPI_REPL_DONT_LOAD` ·
**Flag:** `-x/--dont-load` (repeatable, adds to the configured list)

Models to leave out. Each entry can be:

- a model name: `"AuditLog"`
- a dotted path: `"app.models.audit.AuditLog"`
- a module prefix: `"app.models.legacy"` skips every model defined in that module or below
- a glob: `"*Log"`, `"app.models.internal.*"`
- a Tortoise app label: `"events"`

### `model_aliases`

**Type:** table of strings · **Default:** `{}` · **Env:** `FASTAPI_REPL_MODEL_ALIASES` (JSON)

Load models under a different name. Keys are model names or dotted paths:

```toml
[tool.fastapi-repl.model_aliases]
User = "AuthUser"
"app.billing.models.Account" = "BillingAccount"
```

### `collision`

**Type:** `"prefix"`, `"skip"`, `"override"` or `"error"` · **Default:** `"prefix"` ·
**Env:** `FASTAPI_REPL_COLLISION`

What happens when two models have the same name (for example `blog.models.Tag` and
`shop.models.Tag`). Models are processed in order of their module path.

- `prefix`: the first keeps its name, later ones get the module name as a prefix
  (`shop_Tag`). Tortoise models use their app label. A note is shown.
- `skip`: later ones are not loaded.
- `override`: the last one wins.
- `error`: stop with an error that tells you to add an alias.

### `default_imports`

**Type:** boolean · **Default:** `true` · **Env:** `FASTAPI_REPL_DEFAULT_IMPORTS` ·
**Flag:** `--no-helpers`

Import each adapter's helpers, such as `select`, `func` and `selectinload` for
SQLAlchemy or `Q`, `F` and `Count` for Tortoise. The lists are in each ORM's guide.

## Imports and objects

Names are added in this order, and later ones replace earlier ones with the same name:
`await_` helper, `pre_imports`, ORM helpers, models, `app` / `lifespan_state` / adapter
objects (`engine`, `session`), `imports`, `objects`, hook results, `post_imports`.

### `pre_imports`

**Type:** list of import specs · **Default:** `[]` · **Env:** `FASTAPI_REPL_PRE_IMPORTS`

Imported first, so models and helpers override them. Handy to import something that
registers models before discovery runs.

### `imports`

**Type:** list of import specs · **Default:** `[]` · **Env:** `FASTAPI_REPL_IMPORTS` ·
**Flag:** `-I/--import` (repeatable, adds to the configured list)

Your everyday imports: settings, services, utilities.

### `post_imports`

**Type:** list of import specs · **Default:** `[]` · **Env:** `FASTAPI_REPL_POST_IMPORTS`

Imported last, overriding everything else.

### `objects`

**Type:** table of object paths · **Default:** `{}` · **Env:** `FASTAPI_REPL_OBJECTS` (JSON)

Named objects. Unlike `imports`, you choose the name:

```toml
[tool.fastapi-repl.objects]
redis = "app.cache:get_redis()"       # call a factory (awaited if async)
cfg = "app.core.config:settings"      # plain reference
```

### `hooks`

A table with three lists of object paths to callables. Each callable can be sync or
async, and can take either no arguments or one argument: the namespace built so far.

| Key                | Env                                | Called                                               |
| ------------------ | ---------------------------------- | ---------------------------------------------------- |
| `namespace`        | `FASTAPI_REPL_HOOKS__NAMESPACE`    | While building the namespace. Returns a dict of extra names (or `None`). |
| `startup`          | `FASTAPI_REPL_HOOKS__STARTUP`      | After the namespace is ready, before the prompt.     |
| `shutdown`         | `FASTAPI_REPL_HOOKS__SHUTDOWN`     | When the shell exits.                                |

```python title="app/shell.py"
async def extra_names(ns: dict) -> dict:
    admin = await ns["session"].scalar(ns["select"](ns["User"]).where(ns["User"].is_admin))
    return {"admin": admin}
```

## Adapter settings

### `sqlalchemy`

Options for the SQLAlchemy and SQLModel adapters, in `[tool.fastapi-repl.sqlalchemy]`.

| Key               | Default     | Description                                                                 |
| ----------------- | ----------- | --------------------------------------------------------------------------- |
| `engine`          | auto-detect | Object path of your `Engine` or `AsyncEngine`. When omitted, the single engine in memory is used. |
| `session_factory` | none        | Object path of a `sessionmaker` / `async_sessionmaker`. Called to create `session`. |
| `session`         | `true`      | Create a session object.                                                    |
| `session_name`    | `"session"` | Name of the session in the shell.                                           |
| `engine_name`     | `"engine"`  | Name of the engine in the shell.                                            |
| `dispose_engine`  | `true`      | Dispose the engine's connection pool on exit, which avoids warnings from async drivers. |

### `tortoise`

Options for the Tortoise ORM adapter, in `[tool.fastapi-repl.tortoise]`. If Tortoise is
already initialised (for example by your app's lifespan), none of these are needed.

| Key                | Default | Description                                                          |
| ------------------ | ------- | -------------------------------------------------------------------- |
| `config`           | none    | Object path of your `TORTOISE_ORM` dict (or a function returning it). |
| `config_file`      | none    | Path to a Tortoise JSON/YAML config file, relative to the project root. |
| `db_url`           | none    | Database URL, used together with `modules`.                          |
| `modules`          | `{}`    | App label to module list, e.g. `{ models = ["app.models"] }`.        |
| `generate_schemas` | `false` | Create missing tables at startup. Handy for SQLite prototypes.       |

### `plugins`

**Type:** table of tables · **Default:** `{}`

Options for third-party adapters, keyed by adapter name. The adapter reads them from
`self.context.options`:

```toml
[tool.fastapi-repl.plugins.beanie]
database = "app.db:database"
```

## Safety

### `read_only`

**Type:** boolean · **Default:** `false` · **Env:** `FASTAPI_REPL_READ_ONLY` ·
**Flag:** `--read-only / --read-write`

Open every database connection read-only, so nothing you type can change data. Reads
work as normal; writes fail with a database error.

- **PostgreSQL:** every transaction starts with `BEGIN READ ONLY` (SQLAlchemy's
  `postgresql_readonly` option). This is safe behind transaction poolers such as
  PgBouncer, Neon and Supabase. With asyncpg, psycopg or psycopg2 it is applied per
  transaction; pg8000 applies it per connection, which a transaction pooler can bypass.
- **SQLite:** each connection runs `PRAGMA query_only = ON`.

The setting fails closed. If an adapter cannot enforce it (other databases, Tortoise ORM,
or `auto_imports = false`), the shell refuses to start instead of giving you write access.
It applies to the configured engine; the connection pool is reset when the shell starts
and again when it exits, so read-only connections never leak into other code.

This protects against mistakes, not attackers: a determined user can still open a new
connection. For real protection, connect with a database user that only has `SELECT`
rights.

### `rollback_on_error`

**Type:** boolean · **Default:** `true` · **Env:** `FASTAPI_REPL_ROLLBACK_ON_ERROR`

After a statement fails, roll the session back if it cannot be used any more: after a
failed flush (SQLAlchemy refuses to continue until you roll back), or after any database
error on PostgreSQL (which rejects every statement until the transaction ends). A note
tells you that uncommitted changes were discarded. Errors that leave the session usable
are left alone.

Works in IPython, the plain Python shell, bpython (through `await_`), `-c` and `run`. In
ptpython, call `await session.rollback()` yourself.

## SQL logging

### `print_sql`

**Type:** boolean · **Default:** `false` · **Env:** `FASTAPI_REPL_PRINT_SQL` ·
**Flag:** `--print-sql`

Print each SQL statement with syntax highlighting, its parameters and how long it took.
Output goes to stderr, so it never mixes with piped output. Statements run by startup
hooks are not printed.

### `truncate_sql`

**Type:** integer · **Default:** none · **Env:** `FASTAPI_REPL_TRUNCATE_SQL` ·
**Flag:** `--truncate-sql N` (implies `--print-sql`)

Cut printed statements to N characters.

### `print_sql_location`

**Type:** boolean · **Default:** `false` · **Env:** `FASTAPI_REPL_PRINT_SQL_LOCATION` ·
**Flag:** `--print-sql-location` (implies `--print-sql`)

Show the file and line of your code that triggered each query. Available for sync
SQLAlchemy; async drivers run queries in a separate greenlet where the caller is not
visible.

## Output

### `quiet`

**Type:** boolean · **Default:** `false` · **Env:** `FASTAPI_REPL_QUIET` · **Flag:** `-q/--quiet`

Do not print the startup banner.

### `quiet_load`

**Type:** boolean · **Default:** `false` · **Env:** `FASTAPI_REPL_QUIET_LOAD` ·
**Flag:** `--quiet-load`

Do not report things that failed to import.

### `verbose`

**Type:** boolean · **Default:** `false` · **Env:** `FASTAPI_REPL_VERBOSE` ·
**Flag:** `-v/--verbose`

After the banner, print a table of every name in the shell and where it came from
(the same table as `fastapi-repl imports`).

### `strict`

**Type:** boolean · **Default:** `false` · **Env:** `FASTAPI_REPL_STRICT` · **Flag:** `--strict`

Stop with an error when anything fails to import, instead of warning and carrying on.
Useful in CI (`fastapi-repl --strict -c "pass"` checks that everything imports).

### `banner`

**Type:** string · **Default:** none · **Env:** `FASTAPI_REPL_BANNER`

Extra text shown at the bottom of the banner, for example a reminder that you are
connected to production.
