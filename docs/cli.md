# CLI reference

An interactive shell for FastAPI (and any ASGI) projects, with your models, database session and imports preloaded, and top-level <span style="font-weight: bold">await</span>.

Running <span style="font-weight: bold">fastapi-repl</span> with no command starts the shell.

**Usage**:

```console
$ fastapi-repl [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--version`: Show the version and exit.
* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

Docs: https://huzzy619.github.io/fastapi-repl

**Commands**:

* `shell`: Start an interactive shell with your...
* `run`: Run a script with the shell namespace...
* `imports`: List every name the shell would load, and...
* `config`: Show the resolved configuration and where...
* `init`: Detect your project layout and write a...
* `doctor`: Check your setup: config, interfaces,...

## `fastapi-repl shell`

Start an interactive shell with your project loaded. <span style="color: #7f7f7f; text-decoration-color: #7f7f7f">(default command)</span>

**Usage**:

```console
$ fastapi-repl shell [OPTIONS]
```

**Options**:

* `-i, --interface <auto|ipython|ptpython|ptipython|bpython|python>`: Interactive shell to use. <span style="font-style: italic">auto</span> picks the first installed one from interface_order.
* `--ipython`: Use IPython.
* `--ptpython`: Use ptpython.
* `--ptipython`: Use ptpython on top of IPython.
* `--bpython`: Use bpython.
* `--plain`: Use the plain Python shell.
* `--notebook`: Open Jupyter Notebook with a preloaded kernel.
* `--lab`: Open JupyterLab with a preloaded kernel.
* `--kernel`: Run a preloaded IPython kernel (for Jupyter clients).
* `--connection-file <str>`: Kernel connection file (with --kernel).
* `--startup / --no-startup`: Run $PYTHONSTARTUP and ~/.pythonrc.py (plain Python shell).
* `--ipython-arguments <str>`: Extra arguments for IPython, as one string.
* `--jupyter-arguments <str>`: Extra arguments for Jupyter, as one string.
* `-c, --command <str>`: Run this code instead of starting a shell. <span style="font-style: italic">await</span> works.
* `--config <file>`: Config file to use (<span style="font-style: italic">pyproject.toml</span> or <span style="font-style: italic">fastapi-repl.toml</span>). Found automatically by default.
* `--env-file <str>`: Load this .env file first.
* `--app <str>`: ASGI app import path, e.g. <span style="font-style: italic">main:app</span>.
* `--lifespan / --no-lifespan`: Run the app&#x27;s startup and shutdown (ASGI lifespan).
* `--read-only / --read-write`: Open database connections read-only. Refuses to start if that cannot be enforced.
* `-m, --models <str>`: Module or package with models. Repeatable. Replaces the configured list.
* `--no-models`: Do not load models.
* `-x, --dont-load <str>`: Skip models by name, dotted path, module prefix or glob. Repeatable.
* `-I, --import <str>`: Extra import, e.g. <span style="font-style: italic">&#x27;from app.core import settings&#x27;</span>. Repeatable.
* `--no-imports`: Start with no automatic imports at all.
* `--no-helpers`: Skip ORM helpers such as select and func.
* `--strict`: Fail if anything cannot be imported.
* `--print-sql`: Print SQL statements as they run.
* `--truncate-sql <int range>`: Truncate printed SQL to N characters.  [x&gt;=1]
* `--print-sql-location`: Show which line of your code ran each query.
* `-q, --quiet`: Hide the banner.
* `--quiet-load`: Hide import errors.
* `-v, --verbose`: List every name and where it came from.
* `--help`: Show this message and exit.

Examples:

fastapi-repl  (start the shell)

fastapi-repl --ptpython --print-sql

fastapi-repl -c 'print(await session.scalar(select(func.count(User.id))))'

echo 'print(app.routes)' | fastapi-repl

## `fastapi-repl run`

Run a script with the shell namespace preloaded. Top-level <span style="font-style: italic">await</span> works.

Arguments after the script (use <span style="font-weight: bold">--</span> to separate them) become <span style="font-style: italic">sys.argv[1:]</span>.

**Usage**:

```console
$ fastapi-repl run [OPTIONS] {target}
```

**Arguments**:

* `target`: A script path (<span style="font-style: italic">scripts/seed.py</span>) or module (<span style="font-style: italic">scripts.seed</span>).  [required]

**Options**:

* `-f, --func <str>`: Also call this function from the script (sync or async) after it runs.
* `--config <file>`: Config file to use (<span style="font-style: italic">pyproject.toml</span> or <span style="font-style: italic">fastapi-repl.toml</span>). Found automatically by default.
* `--env-file <str>`: Load this .env file first.
* `--app <str>`: ASGI app import path, e.g. <span style="font-style: italic">main:app</span>.
* `--lifespan / --no-lifespan`: Run the app&#x27;s startup and shutdown (ASGI lifespan).
* `--read-only / --read-write`: Open database connections read-only. Refuses to start if that cannot be enforced.
* `-m, --models <str>`: Module or package with models. Repeatable. Replaces the configured list.
* `--no-models`: Do not load models.
* `-x, --dont-load <str>`: Skip models by name, dotted path, module prefix or glob. Repeatable.
* `-I, --import <str>`: Extra import, e.g. <span style="font-style: italic">&#x27;from app.core import settings&#x27;</span>. Repeatable.
* `--no-imports`: Start with no automatic imports at all.
* `--no-helpers`: Skip ORM helpers such as select and func.
* `--strict`: Fail if anything cannot be imported.
* `--print-sql`: Print SQL statements as they run.
* `--truncate-sql <int range>`: Truncate printed SQL to N characters.  [x&gt;=1]
* `--print-sql-location`: Show which line of your code ran each query.
* `--quiet-load`: Hide import errors.
* `--help`: Show this message and exit.

Examples:

fastapi-repl run scripts/seed.py

fastapi-repl run scripts.seed --func main -- --count 10

## `fastapi-repl imports`

List every name the shell would load, and where it comes from.

**Usage**:

```console
$ fastapi-repl imports [OPTIONS]
```

**Options**:

* `--json`: Output JSON.
* `--config <file>`: Config file to use (<span style="font-style: italic">pyproject.toml</span> or <span style="font-style: italic">fastapi-repl.toml</span>). Found automatically by default.
* `--env-file <str>`: Load this .env file first.
* `--app <str>`: ASGI app import path, e.g. <span style="font-style: italic">main:app</span>.
* `--lifespan / --no-lifespan`: Run the app&#x27;s startup and shutdown (ASGI lifespan).
* `-m, --models <str>`: Module or package with models. Repeatable. Replaces the configured list.
* `--no-models`: Do not load models.
* `-x, --dont-load <str>`: Skip models by name, dotted path, module prefix or glob. Repeatable.
* `-I, --import <str>`: Extra import, e.g. <span style="font-style: italic">&#x27;from app.core import settings&#x27;</span>. Repeatable.
* `--no-helpers`: Skip ORM helpers such as select and func.
* `--help`: Show this message and exit.

## `fastapi-repl config`

Show the resolved configuration and where each value came from.

**Usage**:

```console
$ fastapi-repl config [OPTIONS]
```

**Options**:

* `--json`: Output JSON.
* `--changed`: Only show settings that are not defaults.
* `--config <file>`: Config file to use (<span style="font-style: italic">pyproject.toml</span> or <span style="font-style: italic">fastapi-repl.toml</span>). Found automatically by default.
* `--env-file <str>`: Load this .env file first.
* `--help`: Show this message and exit.

## `fastapi-repl init`

Detect your project layout and write a starter configuration.

**Usage**:

```console
$ fastapi-repl init [OPTIONS]
```

**Options**:

* `--standalone`: Write <span style="font-style: italic">fastapi-repl.toml</span> instead of pyproject.toml.
* `--dry-run`: Print the config without writing it.
* `--force`: Overwrite an existing fastapi-repl.toml.
* `--path <directory>`: Project directory. Defaults to the detected project root.
* `--help`: Show this message and exit.

## `fastapi-repl doctor`

Check your setup: config, interfaces, adapters and imports.

**Usage**:

```console
$ fastapi-repl doctor [OPTIONS]
```

**Options**:

* `--config <file>`: Config file to use (<span style="font-style: italic">pyproject.toml</span> or <span style="font-style: italic">fastapi-repl.toml</span>). Found automatically by default.
* `--env-file <str>`: Load this .env file first.
* `--lifespan / --no-lifespan`: Run the app&#x27;s startup and shutdown (ASGI lifespan).
* `--help`: Show this message and exit.
