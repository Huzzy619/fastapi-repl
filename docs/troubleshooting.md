# Troubleshooting

Start with the doctor. It checks the config, the installed interfaces and adapters,
and loads your project the way the shell would, reporting everything that fails to
import:

```console
$ fastapi-repl doctor
```

Then `fastapi-repl config` shows what was loaded from where, and
`fastapi-repl imports` shows every name in the shell.

## "No models found"

- Nothing imported the models. Set `models = ["app.models"]` (a package is imported
  recursively), or set `app` so that the app imports them.
- The models are excluded by `dont_load`. Check with `fastapi-repl config`.
- The wrong adapter is active. `fastapi-repl doctor` lists the detected adapters; set
  `adapters = ["sqlalchemy"]` to choose.

## `ModuleNotFoundError: No module named 'app'`

The project root is not where your packages are. fastapi-repl adds `pythonpath`
(relative to the project root) to `sys.path`. For a src layout use
`pythonpath = ["src"]`. Run `fastapi-repl config` to see which root was found.

## Settings fail to load (missing environment variables)

Set `env_file = ".env"` so the variables are loaded before your code is imported.

## "Found 2 SQLAlchemy engines"

The SQLAlchemy adapter found more than one engine in memory and does not guess. Set
`[tool.fastapi-repl.sqlalchemy] engine = "app.db:engine"`.

## Errors about loops, such as "attached to a different loop"

These happen when a connection was created on a loop other than the shell's. Common
causes:

- Calling `asyncio.run()` yourself at the prompt. Use `await` instead.
- An engine or client created at import time *and* used by a lifespan running on
  another loop. Let fastapi-repl run the lifespan (`lifespan = true`) instead of
  starting it yourself.

## `SyntaxError: 'await' outside function`

You are in bpython, or in a function you defined at the prompt. Use `await_(...)`.

## A name I expected is missing, or has a different value

Several sources can define the same name; later ones win. The order is described in
[Imports and objects](configuration.md#imports-and-objects), and
`fastapi-repl imports` shows the source of each name.

## IPython is installed but the plain shell starts

IPython is not installed in the same environment as fastapi-repl. With uv, check that
the extra is in the group you synced: `uv add --dev "fastapi-repl[ipython]"`.

## Warnings about the event loop being closed at exit

A connection outlived the loop. Make sure `dispose_engine` is on (the default), and
close any clients you create in `objects` factories: objects with `close()` or
`aclose()` are closed for you.

## Something else

Run with `--strict` to turn warnings into errors with full tracebacks, and please
[open an issue](https://github.com/Huzzy619/fastapi-repl/issues) with the output of
`fastapi-repl doctor`.
