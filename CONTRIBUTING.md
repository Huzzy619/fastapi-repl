# Contributing

Thanks for helping. Bug reports, docs fixes and new adapters are all welcome.

## Setup

The project uses [uv](https://docs.astral.sh/uv/).

```console
git clone https://github.com/Huzzy619/fastapi-repl
cd fastapi-repl
uv sync
```

`uv sync` installs the package in editable mode with the `dev` group, which includes
every supported ORM and the IPython and ptpython interfaces.

## Checks

```console
uv run pytest                 # tests
uv run ruff check .           # lint
uv run ruff format .          # format
uv run pyright                # types
```

CI runs these on Python 3.11 to 3.14 (plus macOS and Windows), against the oldest
dependency versions we allow, and builds the docs in strict mode.

## Layout

```text
src/fastapi_repl/
  cli.py            Typer app: shell, run, imports, config, init, doctor
  config.py         ReplConfig model and the loader (pyproject, toml, env, flags)
  session.py        ReplSession: builds the namespace and cleans up
  runtime.py        The session event loop and the ASGI lifespan runner
  namespace.py      Namespace groups, collisions, aliases, dont_load
  imports.py        Import specs and object paths
  sql.py            SQL printer for --print-sql
  banner.py         Startup banner
  execute.py        -c, stdin and `run` with top-level await
  api.py            embed(), build_namespace(), start_shell()
  init_project.py   Project detection for `init`
  adapters/         ORMAdapter base class and built-in adapters
  interfaces/       IPython, ptpython, bpython, plain Python, Jupyter
tests/
  fixtures/         Small example projects used by the tests
docs/               MkDocs site
```

## Tests

- Each fixture project in `tests/fixtures` is a tiny, realistic app. Prefer adding to a
  fixture over mocking.
- `tests/test_interfaces.py` drives real interactive shells through a pseudo-terminal.
  These tests are skipped on Windows.
- `tests/test_docs.py` checks the documentation: TOML examples must be valid config,
  Python examples marked `<!-- test: <fixture> -->` must run against that fixture,
  every setting must be documented in `docs/configuration.md`, and `docs/cli.md` must be
  up to date.

## Docs

```console
uv run --group docs mkdocs serve
```

After changing CLI options, regenerate the CLI reference:

```console
uv run typer fastapi_repl.cli utils docs --name fastapi-repl --title "CLI reference" --output docs/cli.md
```

When adding a setting, document it in `docs/configuration.md` (the tests will remind
you).

## Adding an adapter

Adapters for popular ORMs can live in this repo; niche ones work well as separate
packages using the `fastapi_repl.adapters` entry point. Either way, start with
[Writing an adapter](docs/guides/writing-adapters.md). A built-in adapter needs:

1. The adapter in `src/fastapi_repl/adapters/`.
2. An entry point and an optional extra in `pyproject.toml`.
3. A fixture project and tests, including `--print-sql`.
4. A guide in `docs/guides/` and a line in the README.

## Releasing

Releases are published by `.github/workflows/release.yml` using PyPI trusted
publishing, so no token is stored anywhere.

One-time setup: on pypi.org, add a trusted publisher for this repository with workflow
`release.yml` and environment `pypi`, and create the `pypi` environment in the GitHub
repository settings (optionally requiring approval).

For each release:

1. Update `src/fastapi_repl/__about__.py` and move the `Unreleased` notes in
   `CHANGELOG.md` under the new version.
2. Commit, then tag and push: `git tag v0.2.0 && git push origin v0.2.0`.
3. The workflow checks that the tag matches the version, runs the tests, publishes to
   PyPI and creates a GitHub release.
