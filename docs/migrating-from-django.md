# Coming from Django

If you have used `manage.py shell` or django-extensions' `shell_plus`, you already know
how fastapi-repl works. This page maps the options you know to their equivalents.

## `manage.py shell`

| Django                                 | fastapi-repl                                   |
| -------------------------------------- | ---------------------------------------------- |
| `manage.py shell`                      | `fastapi-repl`                                 |
| `-i ipython` / `-i bpython` / `-i python` | `-i ipython`, or `--ipython`, `--bpython`, `--plain` |
| `-c "code"`                            | `-c "code"` (with top-level `await`)           |
| Code on stdin                          | Code on stdin                                  |
| `--no-startup`                         | `--no-startup`                                 |
| `--no-imports` (Django 5.2)            | `--no-imports`                                 |
| `-v 2` to list auto-imports            | `-v`, or `fastapi-repl imports`                |
| `get_auto_imports()` override          | `imports`, `objects` and namespace hooks       |
| `settings.py`                          | `[tool.fastapi-repl]` in `pyproject.toml`      |

## `shell_plus`

| shell_plus                                 | fastapi-repl                                         |
| ------------------------------------------ | ---------------------------------------------------- |
| Loads every model                          | Every model, found through the ORM                   |
| `SHELL_PLUS_DONT_LOAD`                     | [`dont_load`](configuration.md#dont_load), `-x/--dont-load` |
| `SHELL_PLUS_MODEL_ALIASES`                 | [`model_aliases`](configuration.md#model_aliases)    |
| `SHELL_PLUS_APP_PREFIXES` and collision prefixes | [`collision = "prefix"`](configuration.md#collision) |
| `SHELL_PLUS_PRE_IMPORTS`                   | [`pre_imports`](configuration.md#pre_imports)        |
| `SHELL_PLUS_IMPORTS`                       | [`imports`](configuration.md#imports), `-I/--import` |
| `SHELL_PLUS_POST_IMPORTS`                  | [`post_imports`](configuration.md#post_imports)      |
| `SHELL_PLUS_DONT_LOAD_DEFAULT_IMPORTS`     | [`default_imports = false`](configuration.md#default_imports), `--no-helpers` |
| Django helpers (`Q`, `F`, `Count`...)      | ORM helpers (`select`, `func`... or `Q`, `F`, `Count` for Tortoise) |
| `--print-sql`                              | `--print-sql`                                        |
| `--truncate-sql`                           | `--truncate-sql`                                     |
| `--print-sql-location`                     | `--print-sql-location` (sync engines)                |
| `--quiet-load`                             | `--quiet-load`                                       |
| `SHELL_PLUS_PRINT_SQL`                     | [`print_sql = true`](configuration.md#print_sql)     |
| `SHELL_PLUS = "ipython"`                   | [`interface = "ipython"`](configuration.md#interface) |
| `SHELL_PLUS_PRE_IMPORTS` for side effects  | `pre_imports` or startup hooks                       |
| `--ipython`, `--ptpython`, `--ptipython`, `--bpython`, `--plain` | Same flags               |
| `--notebook`, `--lab`, `--kernel`          | Same flags                                           |
| `IPYTHON_ARGUMENTS`, `NOTEBOOK_ARGUMENTS`  | `ipython_arguments`, `jupyter_arguments`             |
| `--command`                                | `-c/--command`                                       |
| `runscript`                                | `fastapi-repl run`                                   |

## What is different

- **There is no settings module.** Configuration is TOML plus environment variables, so
  personal preferences do not end up in the team config.
- **Models come from your ORM**, not an app registry. Point `models` at your model
  packages, or let the app import them.
- **The database session is an object you use.** Django's ORM hides the connection;
  SQLAlchemy and friends need a session, so `session` is created for you and closed on
  exit. Remember to `commit()`.
- **Async is first-class.** `await` works at the prompt and in scripts. Django's shell
  refuses async ORM calls in many places.
- **The app's lifespan is optional.** Django has no equivalent; think of it as running
  `AppConfig.ready()` for the services your app starts.
