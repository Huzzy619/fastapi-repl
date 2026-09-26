# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0]

First release.

### Added

- `fastapi-repl` command that opens a shell with models, ORM helpers, engine, session
  and configured imports loaded.
- Adapters for SQLAlchemy 2.x (sync and async), SQLModel and Tortoise ORM, and a plugin
  API with the `fastapi_repl.adapters` entry point group.
- IPython, ptpython, ptipython, bpython, plain Python and Jupyter (notebook, lab,
  kernel) interfaces, with top-level `await` on one persistent event loop.
- Configuration in `[tool.fastapi-repl]`, `fastapi-repl.toml`, `FASTAPI_REPL_*`
  environment variables and flags, with `.env` loading.
- shell_plus features: `dont_load`, `model_aliases`, collision prefixes, pre/post
  imports, `--print-sql`, `--truncate-sql`, `--print-sql-location`, `--quiet-load`.
- Optional ASGI lifespan support for any ASGI 3 framework.
- `-c`, stdin and `run` for scripts, with `await` support.
- `init`, `config`, `imports` and `doctor` commands.
- Python API: `embed()`, `build_namespace()` and `start_shell()`.
- `read_only` setting and `--read-only` flag (PostgreSQL and SQLite), which refuses to
  start when it cannot be enforced.
- `rollback_on_error`: the session is rolled back after a statement leaves it unusable.
- The banner and `doctor` show the connected database, with the password hidden.
- Generator factories (FastAPI-style dependencies) in `objects` and import specs.
- History files are created readable only by the current user.
- Command-line flags now apply to Jupyter kernels started with `--notebook` / `--lab`.

[Unreleased]: https://github.com/Huzzy619/fastapi-repl/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Huzzy619/fastapi-repl/releases/tag/v0.1.0
