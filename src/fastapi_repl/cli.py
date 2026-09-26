"""The ``fastapi-repl`` command-line interface."""

from __future__ import annotations

import io
import json
import select
import shlex
import sys
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum, StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.syntax import Syntax
from rich.table import Table
from typer.core import TyperGroup

from fastapi_repl.__about__ import __version__
from fastapi_repl.banner import render_banner, render_imports, render_notes
from fastapi_repl.config import (
    CONFIG_FILENAME,
    ENV_PREFIX,
    PYPROJECT_FILENAME,
    PYPROJECT_TABLE,
    SECTION_MODELS,
    LoadedConfig,
    ReplConfig,
    find_project_root,
    load_config,
)
from fastapi_repl.errors import ReplError
from fastapi_repl.execute import resolve_script, run_script, run_source
from fastapi_repl.interfaces import INTERFACES, select_interface
from fastapi_repl.interfaces.base import InterfaceContext
from fastapi_repl.session import ReplSession

console = Console()
err_console = Console(stderr=True)

_PACKAGE_DIR = str(Path(__file__).resolve().parent)


class DefaultCommandGroup(TyperGroup):
    """A group that runs ``shell`` when no sub-command is given.

    This makes ``fastapi-repl --ipython`` behave like ``manage.py shell_plus --ipython``.
    """

    default_command = "shell"
    group_options = frozenset(
        {"--help", "-h", "--version", "--install-completion", "--show-completion"}
    )

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if not args or (args[0].startswith("-") and args[0] not in self.group_options):
            args = [self.default_command, *args]
        return super().parse_args(ctx, args)


app = typer.Typer(
    name="fastapi-repl",
    cls=DefaultCommandGroup,
    help=(
        "An interactive shell for FastAPI (and any ASGI) projects, with your models, "
        "database session and imports preloaded, and top-level [bold]await[/bold].\n\n"
        "Running [bold]fastapi-repl[/bold] with no command starts the shell."
    ),
    epilog="Docs: https://huzzy619.github.io/fastapi-repl",
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
    pretty_exceptions_enable=False,
    no_args_is_help=False,
)


class InterfaceChoice(StrEnum):
    auto = "auto"
    ipython = "ipython"
    ptpython = "ptpython"
    ptipython = "ptipython"
    bpython = "bpython"
    python = "python"


# Shared options

PANEL_PROJECT = "Project"
PANEL_LOADING = "Loading"
PANEL_SQL = "SQL"
PANEL_OUTPUT = "Output"
PANEL_INTERFACE = "Interface"
PANEL_EXEC = "Run code"

ConfigOpt = Annotated[
    Path | None,
    typer.Option(
        "--config",
        help="Config file to use ([i]pyproject.toml[/i] or [i]fastapi-repl.toml[/i]). "
        "Found automatically by default.",
        rich_help_panel=PANEL_PROJECT,
        dir_okay=False,
    ),
]
EnvFileOpt = Annotated[
    str | None,
    typer.Option(
        "--env-file", help="Load this .env file first.", rich_help_panel=PANEL_PROJECT
    ),
]
AppOpt = Annotated[
    str | None,
    typer.Option(
        "--app",
        help="ASGI app import path, e.g. [i]main:app[/i].",
        rich_help_panel=PANEL_PROJECT,
    ),
]
LifespanOpt = Annotated[
    bool | None,
    typer.Option(
        "--lifespan/--no-lifespan",
        help="Run the app's startup and shutdown (ASGI lifespan).",
        rich_help_panel=PANEL_PROJECT,
        show_default=False,
    ),
]
ReadOnlyOpt = Annotated[
    bool | None,
    typer.Option(
        "--read-only/--read-write",
        help="Open database connections read-only. Refuses to start if that cannot be enforced.",
        rich_help_panel=PANEL_PROJECT,
        show_default=False,
    ),
]
ModelsOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--models",
        "-m",
        help="Module or package with models. Repeatable. Replaces the configured list.",
        rich_help_panel=PANEL_LOADING,
    ),
]
NoModelsOpt = Annotated[
    bool,
    typer.Option(
        "--no-models", help="Do not load models.", rich_help_panel=PANEL_LOADING
    ),
]
DontLoadOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--dont-load",
        "-x",
        help="Skip models by name, dotted path, module prefix or glob. Repeatable.",
        rich_help_panel=PANEL_LOADING,
    ),
]
ImportOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--import",
        "-I",
        help="Extra import, e.g. [i]'from app.core import settings'[/i]. Repeatable.",
        rich_help_panel=PANEL_LOADING,
    ),
]
NoImportsOpt = Annotated[
    bool,
    typer.Option(
        "--no-imports",
        help="Start with no automatic imports at all.",
        rich_help_panel=PANEL_LOADING,
    ),
]
NoHelpersOpt = Annotated[
    bool,
    typer.Option(
        "--no-helpers",
        help="Skip ORM helpers such as select and func.",
        rich_help_panel=PANEL_LOADING,
    ),
]
StrictOpt = Annotated[
    bool | None,
    typer.Option(
        "--strict",
        help="Fail if anything cannot be imported.",
        rich_help_panel=PANEL_LOADING,
    ),
]
PrintSqlOpt = Annotated[
    bool | None,
    typer.Option(
        "--print-sql",
        help="Print SQL statements as they run.",
        rich_help_panel=PANEL_SQL,
    ),
]
TruncateSqlOpt = Annotated[
    int | None,
    typer.Option(
        "--truncate-sql",
        help="Truncate printed SQL to N characters.",
        rich_help_panel=PANEL_SQL,
        min=1,
    ),
]
SqlLocationOpt = Annotated[
    bool | None,
    typer.Option(
        "--print-sql-location",
        help="Show which line of your code ran each query.",
        rich_help_panel=PANEL_SQL,
    ),
]
QuietOpt = Annotated[
    bool | None,
    typer.Option(
        "--quiet", "-q", help="Hide the banner.", rich_help_panel=PANEL_OUTPUT
    ),
]
QuietLoadOpt = Annotated[
    bool | None,
    typer.Option(
        "--quiet-load", help="Hide import errors.", rich_help_panel=PANEL_OUTPUT
    ),
]
VerboseOpt = Annotated[
    bool | None,
    typer.Option(
        "--verbose",
        "-v",
        help="List every name and where it came from.",
        rich_help_panel=PANEL_OUTPUT,
    ),
]


def _cli_overrides(**values: Any) -> dict[str, Any]:
    """Translate flag values into config keys. ``None`` means "not given"."""
    mapping = {
        "app": "app",
        "env_file": "env_file",
        "lifespan": "lifespan",
        "read_only": "read_only",
        "models": "models",
        "strict": "strict",
        "print_sql": "print_sql",
        "truncate_sql": "truncate_sql",
        "print_sql_location": "print_sql_location",
        "quiet": "quiet",
        "quiet_load": "quiet_load",
        "verbose": "verbose",
        "interface": "interface",
        "startup": "startup",
    }
    overrides: dict[str, Any] = {}
    for flag, key in mapping.items():
        value = values.get(flag)
        if value is None or value == []:
            continue
        overrides[key] = value.value if isinstance(value, Enum) else value
    if values.get("no_models"):
        overrides["load_models"] = False
    if values.get("no_imports"):
        overrides["auto_imports"] = False
    if values.get("no_helpers"):
        overrides["default_imports"] = False
    if values.get("truncate_sql") is not None or values.get("print_sql_location"):
        overrides.setdefault("print_sql", True)
    return overrides


def _load(
    config_file: Path | None,
    *,
    extra_imports: list[str] | None = None,
    dont_load: list[str] | None = None,
    ipython_arguments: str | None = None,
    jupyter_arguments: str | None = None,
    **values: Any,
) -> LoadedConfig:
    loaded = load_config(cli=_cli_overrides(**values), config_file=config_file)
    update: dict[str, Any] = {}
    config = loaded.config
    if extra_imports:
        update["imports"] = [*config.imports, *extra_imports]
        loaded.sources["imports"] = "command line"
    if dont_load:
        update["dont_load"] = [*config.dont_load, *dont_load]
        loaded.sources["dont_load"] = "command line"
    if ipython_arguments:
        update["ipython_arguments"] = shlex.split(ipython_arguments)
        loaded.sources["ipython_arguments"] = "command line"
    if jupyter_arguments:
        update["jupyter_arguments"] = shlex.split(jupyter_arguments)
        loaded.sources["jupyter_arguments"] = "command line"
    if update:
        loaded.config = config.model_copy(update=update)
    return loaded


def _flags_as_env(loaded: LoadedConfig) -> dict[str, str]:
    """Command-line settings as ``FASTAPI_REPL_*`` variables, for kernel subprocesses."""
    env: dict[str, str] = {}
    for key, source in loaded.sources.items():
        if source != "command line" or "." in key:
            continue
        value = getattr(loaded.config, key)
        env[f"{ENV_PREFIX}{key.upper()}"] = (
            value if isinstance(value, str) else json.dumps(value)
        )
    return env


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except ReplError as exc:
        err_console.print(f"[bold red]error:[/] {escape(str(exc))}")
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        err_console.print()
        raise typer.Exit(130) from None


def _print_user_traceback(exc: BaseException) -> None:
    """Print a traceback without fastapi-repl's own frames."""
    te = traceback.TracebackException.from_exception(exc)
    te.stack = traceback.StackSummary.from_list(
        [f for f in te.stack if not f.filename.startswith(_PACKAGE_DIR)]
    )
    sys.stderr.write("".join(te.format()))


def _read_stdin() -> str | None:
    """Return piped stdin, Django-style: only when stdin is not a TTY and has data."""
    stdin = sys.stdin
    if stdin is None:
        return None
    try:
        if stdin.isatty():
            return None
    except (AttributeError, ValueError):
        return None
    if sys.platform != "win32":
        try:
            ready, _, _ = select.select([stdin], [], [], 0)
        except (OSError, ValueError, TypeError, io.UnsupportedOperation):
            ready = [stdin]
        if not ready:
            return None
    return stdin.read()


def _start_session(loaded: LoadedConfig, *, show_status: bool) -> ReplSession:
    session = ReplSession(loaded, console=console, err_console=err_console)
    if show_status and err_console.is_terminal:
        with err_console.status("Loading your project…", spinner="dots"):
            session.start()
    else:
        session.start()
    return session


def _resolve_interface(
    interface: InterfaceChoice | None, shortcuts: dict[str, bool]
) -> str | None:
    chosen = [name for name, on in shortcuts.items() if on]
    if len(chosen) > 1 or (chosen and interface is not None):
        flags = ", ".join(f"--{c}" for c in chosen)
        if interface is not None:
            flags += f", --interface {interface.value}"
        raise ReplError(f"Choose a single interface (got {flags}).")
    if chosen:
        return "python" if chosen[0] == "plain" else chosen[0]
    return interface.value if interface is not None else None


# Commands


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"fastapi-repl {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = None,
) -> None:
    pass


@app.command(
    "shell",
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog=(
        "Examples:\n\n"
        "fastapi-repl  (start the shell)\n\n"
        "fastapi-repl --ptpython --print-sql\n\n"
        "fastapi-repl -c 'print(await session.scalar(select(func.count(User.id))))'\n\n"
        "echo 'print(app.routes)' | fastapi-repl"
    ),
)
def shell(
    interface: Annotated[
        InterfaceChoice | None,
        typer.Option(
            "--interface",
            "-i",
            help="Interactive shell to use. [i]auto[/i] picks the first installed one "
            "from interface_order.",
            rich_help_panel=PANEL_INTERFACE,
            case_sensitive=False,
        ),
    ] = None,
    ipython: Annotated[
        bool,
        typer.Option("--ipython", help="Use IPython.", rich_help_panel=PANEL_INTERFACE),
    ] = False,
    ptpython: Annotated[
        bool,
        typer.Option(
            "--ptpython", help="Use ptpython.", rich_help_panel=PANEL_INTERFACE
        ),
    ] = False,
    ptipython: Annotated[
        bool,
        typer.Option(
            "--ptipython",
            help="Use ptpython on top of IPython.",
            rich_help_panel=PANEL_INTERFACE,
        ),
    ] = False,
    bpython: Annotated[
        bool,
        typer.Option("--bpython", help="Use bpython.", rich_help_panel=PANEL_INTERFACE),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Use the plain Python shell.",
            rich_help_panel=PANEL_INTERFACE,
        ),
    ] = False,
    notebook: Annotated[
        bool,
        typer.Option(
            "--notebook",
            help="Open Jupyter Notebook with a preloaded kernel.",
            rich_help_panel=PANEL_INTERFACE,
        ),
    ] = False,
    lab: Annotated[
        bool,
        typer.Option(
            "--lab",
            help="Open JupyterLab with a preloaded kernel.",
            rich_help_panel=PANEL_INTERFACE,
        ),
    ] = False,
    kernel: Annotated[
        bool,
        typer.Option(
            "--kernel",
            help="Run a preloaded IPython kernel (for Jupyter clients).",
            rich_help_panel=PANEL_INTERFACE,
        ),
    ] = False,
    connection_file: Annotated[
        str | None,
        typer.Option(
            "--connection-file",
            help="Kernel connection file (with --kernel).",
            rich_help_panel=PANEL_INTERFACE,
        ),
    ] = None,
    startup: Annotated[
        bool | None,
        typer.Option(
            "--startup/--no-startup",
            help="Run $PYTHONSTARTUP and ~/.pythonrc.py (plain Python shell).",
            rich_help_panel=PANEL_INTERFACE,
            show_default=False,
        ),
    ] = None,
    ipython_arguments: Annotated[
        str | None,
        typer.Option(
            "--ipython-arguments",
            help="Extra arguments for IPython, as one string.",
            rich_help_panel=PANEL_INTERFACE,
        ),
    ] = None,
    jupyter_arguments: Annotated[
        str | None,
        typer.Option(
            "--jupyter-arguments",
            help="Extra arguments for Jupyter, as one string.",
            rich_help_panel=PANEL_INTERFACE,
        ),
    ] = None,
    command: Annotated[
        str | None,
        typer.Option(
            "--command",
            "-c",
            help="Run this code instead of starting a shell. [i]await[/i] works.",
            rich_help_panel=PANEL_EXEC,
        ),
    ] = None,
    config_file: ConfigOpt = None,
    env_file: EnvFileOpt = None,
    app_path: AppOpt = None,
    lifespan: LifespanOpt = None,
    read_only: ReadOnlyOpt = None,
    models: ModelsOpt = None,
    no_models: NoModelsOpt = False,
    dont_load: DontLoadOpt = None,
    extra_imports: ImportOpt = None,
    no_imports: NoImportsOpt = False,
    no_helpers: NoHelpersOpt = False,
    strict: StrictOpt = None,
    print_sql: PrintSqlOpt = None,
    truncate_sql: TruncateSqlOpt = None,
    print_sql_location: SqlLocationOpt = None,
    quiet: QuietOpt = None,
    quiet_load: QuietLoadOpt = None,
    verbose: VerboseOpt = None,
) -> None:
    """Start an interactive shell with your project loaded. [dim](default command)[/dim]"""
    with _errors():
        chosen = _resolve_interface(
            interface,
            {
                "ipython": ipython,
                "ptpython": ptpython,
                "ptipython": ptipython,
                "bpython": bpython,
                "plain": plain,
            },
        )
        modes = [
            m
            for m, on in (
                ("--notebook", notebook),
                ("--lab", lab),
                ("--kernel", kernel),
                ("--command", command is not None),
            )
            if on
        ]
        if len(modes) > 1:
            raise ReplError(f"{' and '.join(modes)} cannot be combined.")

        loaded = _load(
            config_file,
            extra_imports=extra_imports,
            dont_load=dont_load,
            ipython_arguments=ipython_arguments,
            jupyter_arguments=jupyter_arguments,
            interface=chosen,
            startup=startup,
            env_file=env_file,
            app=app_path,
            lifespan=lifespan,
            read_only=read_only,
            models=models,
            no_models=no_models,
            no_imports=no_imports,
            no_helpers=no_helpers,
            strict=strict,
            print_sql=print_sql,
            truncate_sql=truncate_sql,
            print_sql_location=print_sql_location,
            quiet=quiet,
            quiet_load=quiet_load,
            verbose=verbose,
        )
        config = loaded.config

        if notebook or lab:
            from fastapi_repl.interfaces.jupyter import launch_jupyter

            code = launch_jupyter(
                "lab" if lab else "notebook",
                root=loaded.root,
                config_file=(
                    config_file.resolve() if config_file else loaded.config_file
                ),
                extra_args=list(config.jupyter_arguments),
                env_overrides=_flags_as_env(loaded),
            )
            raise typer.Exit(code)

        interface_cls = None
        stdin_source = None
        if command is None and not kernel:
            stdin_source = _read_stdin()
            if stdin_source is None:
                interface_cls = select_interface(
                    config.interface, config.interface_order
                )

        session = _start_session(
            loaded, show_status=interface_cls is not None and not kernel
        )
        try:
            namespace = session.namespace.to_dict()
            assert session.runtime is not None
            source = command if command is not None else stdin_source
            if source is not None:
                if not config.quiet_load:
                    render_notes(session, console=err_console)
                try:
                    run_source(
                        source,
                        namespace,
                        session.runtime,
                        filename="<command>" if command is not None else "<stdin>",
                    )
                except SystemExit as exc:
                    raise typer.Exit(
                        exc.code if isinstance(exc.code, int) else 1
                    ) from None
                except Exception as exc:
                    _print_user_traceback(exc)
                    raise typer.Exit(1) from None
                return

            context = InterfaceContext(
                namespace=namespace,
                runtime=session.runtime,
                loaded=loaded,
                console=console,
            )
            if kernel:
                from fastapi_repl.interfaces.jupyter import KernelInterface

                if not KernelInterface.is_available():
                    raise ReplError(
                        f"ipykernel is not installed. Install it with: "
                        f"{KernelInterface.install_hint()}"
                    )
                KernelInterface(context, connection_file=connection_file).start()
                return

            assert interface_cls is not None
            if not config.quiet:
                render_banner(session, interface_cls, console=console)
            else:
                render_notes(session, console=err_console)
            interface_cls(context).start()
        finally:
            session.close()


@app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    epilog=(
        "Examples:\n\n"
        "fastapi-repl run scripts/seed.py\n\n"
        "fastapi-repl run scripts.seed --func main -- --count 10"
    ),
)
def run(
    ctx: typer.Context,
    target: Annotated[
        str,
        typer.Argument(
            help="A script path ([i]scripts/seed.py[/i]) or module ([i]scripts.seed[/i]).",
            show_default=False,
        ),
    ],
    func: Annotated[
        str | None,
        typer.Option(
            "--func",
            "-f",
            help="Also call this function from the script (sync or async) after it runs.",
        ),
    ] = None,
    config_file: ConfigOpt = None,
    env_file: EnvFileOpt = None,
    app_path: AppOpt = None,
    lifespan: LifespanOpt = None,
    read_only: ReadOnlyOpt = None,
    models: ModelsOpt = None,
    no_models: NoModelsOpt = False,
    dont_load: DontLoadOpt = None,
    extra_imports: ImportOpt = None,
    no_imports: NoImportsOpt = False,
    no_helpers: NoHelpersOpt = False,
    strict: StrictOpt = None,
    print_sql: PrintSqlOpt = None,
    truncate_sql: TruncateSqlOpt = None,
    print_sql_location: SqlLocationOpt = None,
    quiet_load: QuietLoadOpt = None,
) -> None:
    """Run a script with the shell namespace preloaded. Top-level [i]await[/i] works.

    Arguments after the script (use [bold]--[/bold] to separate them) become [i]sys.argv[1:][/i].
    """
    with _errors():
        loaded = _load(
            config_file,
            extra_imports=extra_imports,
            dont_load=dont_load,
            env_file=env_file,
            app=app_path,
            lifespan=lifespan,
            read_only=read_only,
            models=models,
            no_models=no_models,
            no_imports=no_imports,
            no_helpers=no_helpers,
            strict=strict,
            print_sql=print_sql,
            truncate_sql=truncate_sql,
            print_sql_location=print_sql_location,
            quiet_load=quiet_load,
        )
        session = _start_session(loaded, show_status=False)
        try:
            path = resolve_script(target)
            if not loaded.config.quiet_load:
                render_notes(session, console=err_console)
            assert session.runtime is not None
            try:
                run_script(
                    path,
                    session.namespace.to_dict(),
                    session.runtime,
                    argv=list(ctx.args),
                    func=func,
                )
            except SystemExit as exc:
                raise typer.Exit(exc.code if isinstance(exc.code, int) else 1) from None
            except ReplError:
                raise
            except Exception as exc:
                _print_user_traceback(exc)
                raise typer.Exit(1) from None
        finally:
            session.close()


@app.command("imports")
def imports(
    as_json: Annotated[bool, typer.Option("--json", help="Output JSON.")] = False,
    config_file: ConfigOpt = None,
    env_file: EnvFileOpt = None,
    app_path: AppOpt = None,
    lifespan: LifespanOpt = None,
    models: ModelsOpt = None,
    no_models: NoModelsOpt = False,
    dont_load: DontLoadOpt = None,
    extra_imports: ImportOpt = None,
    no_helpers: NoHelpersOpt = False,
) -> None:
    """List every name the shell would load, and where it comes from."""
    with _errors():
        loaded = _load(
            config_file,
            extra_imports=extra_imports,
            dont_load=dont_load,
            env_file=env_file,
            app=app_path,
            lifespan=lifespan,
            models=models,
            no_models=no_models,
            no_helpers=no_helpers,
        )
        session = _start_session(loaded, show_status=not as_json)
        try:
            if as_json:
                from fastapi_repl.banner import _describe_value

                payload = {
                    "names": [
                        {
                            "name": e.name,
                            "group": e.group,
                            "type": _describe_value(e.value),
                            "source": e.source,
                        }
                        for e in session.namespace.entries.values()
                    ],
                    "failures": [
                        {"what": f.what, "group": f.group, "error": f.message}
                        for f in session.namespace.failures
                    ],
                    "adapters": [a.name for a in session.adapters],
                    "warnings": session.warnings,
                    "notes": session.namespace.notes,
                }
                sys.stdout.write(json.dumps(payload, indent=2) + "\n")
            else:
                render_imports(session, console=console)
                render_notes(session, console=console)
        finally:
            session.close()


def _config_rows(loaded: LoadedConfig) -> list[tuple[str, Any, str]]:
    rows: list[tuple[str, Any, str]] = []
    data = loaded.config.model_dump()
    for key in ReplConfig.model_fields:
        value = data[key]
        if key in SECTION_MODELS or (isinstance(value, dict) and value):
            for sub_key, sub_value in value.items():
                dotted = f"{key}.{sub_key}"
                rows.append((dotted, sub_value, loaded.source_of(dotted)))
        else:
            rows.append((key, value, loaded.source_of(key)))
    return rows


@app.command("config")
def show_config(
    as_json: Annotated[bool, typer.Option("--json", help="Output JSON.")] = False,
    changed: Annotated[
        bool,
        typer.Option("--changed", help="Only show settings that are not defaults."),
    ] = False,
    config_file: ConfigOpt = None,
    env_file: EnvFileOpt = None,
) -> None:
    """Show the resolved configuration and where each value came from."""
    with _errors():
        loaded = _load(config_file, env_file=env_file)
        rows = _config_rows(loaded)
        if changed:
            rows = [r for r in rows if r[2] != "default"]
        if as_json:
            payload = {
                "root": str(loaded.root),
                "files": [str(f) for f in loaded.files],
                "settings": {k: {"value": v, "source": s} for k, v, s in rows},
                "warnings": loaded.warnings,
            }
            sys.stdout.write(json.dumps(payload, indent=2, default=str) + "\n")
            return
        console.print(f"[bold]Project root:[/] {loaded.root}")
        files = (
            ", ".join(str(f) for f in loaded.files) or "[dim]none (using defaults)[/]"
        )
        console.print(f"[bold]Config files:[/] {files}")
        table = Table(expand=False)
        table.add_column("Setting", style="cyan", no_wrap=True)
        table.add_column("Value")
        table.add_column("Source", style="dim")
        for key, value, source in rows:
            style = "" if source != "default" else "dim"
            table.add_row(
                key, escape(json.dumps(value, default=str)), source, style=style
            )
        console.print(table)
        for warning in loaded.warnings:
            console.print(f"[yellow]warning:[/] {escape(warning)}")


@app.command("init")
def init(
    standalone: Annotated[
        bool,
        typer.Option(
            "--standalone",
            help=f"Write [i]{CONFIG_FILENAME}[/i] instead of pyproject.toml.",
        ),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the config without writing it.")
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help=f"Overwrite an existing {CONFIG_FILENAME}."),
    ] = False,
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Project directory. Defaults to the detected project root.",
            file_okay=False,
        ),
    ] = None,
) -> None:
    """Detect your project layout and write a starter configuration."""
    from fastapi_repl.init_project import detect_project, render_toml

    with _errors():
        root = (path or find_project_root()).resolve()
        detection = detect_project(root)
        table = detection.to_config()

        console.print(f"[bold]Project:[/] {root}")
        found = [
            ("ORM", ", ".join(detection.orms) or None),
            ("App", detection.app),
            ("Models", ", ".join(detection.models) or None),
            ("Base", detection.base),
            ("Engine", detection.engine),
            ("Session factory", detection.session_factory),
            ("Tortoise config", detection.tortoise_config),
            (".env", detection.env_file),
        ]
        for label, value in found:
            if value:
                console.print(f"  [green]✓[/] {label}: [cyan]{escape(value)}[/]")

        pyproject = root / PYPROJECT_FILENAME
        use_pyproject = not standalone and pyproject.is_file()
        header = f"tool.{PYPROJECT_TABLE}" if use_pyproject else None
        text = render_toml(table, header=header)
        target = pyproject if use_pyproject else root / CONFIG_FILENAME

        if dry_run:
            console.print(f"\n[bold]Would write to {target.name}:[/]\n")
            console.print(Syntax(text, "toml", theme="ansi_dark"))
            return

        if use_pyproject:
            current = pyproject.read_text(encoding="utf-8")
            if f"[tool.{PYPROJECT_TABLE}" in current:
                raise ReplError(
                    f"{PYPROJECT_FILENAME} already has a [tool.{PYPROJECT_TABLE}] table. "
                    "Edit it directly, or use --dry-run to see the suggested config."
                )
            separator = (
                ""
                if current.endswith("\n\n")
                else ("\n" if current.endswith("\n") else "\n\n")
            )
            pyproject.write_text(current + separator + text, encoding="utf-8")
        else:
            if target.exists() and not force:
                raise ReplError(
                    f"{target} already exists. Use --force to overwrite it."
                )
            target.write_text(text, encoding="utf-8")
        console.print(
            f"\n[green]Wrote config to {target}.[/] Start the shell with [bold]fastapi-repl[/bold]."
        )


@app.command("doctor")
def doctor(
    config_file: ConfigOpt = None,
    env_file: EnvFileOpt = None,
    lifespan: LifespanOpt = None,
) -> None:
    """Check your setup: config, interfaces, adapters and imports."""
    from fastapi_repl.adapters import available_adapters, load_adapter_class

    problems = 0
    with _errors():
        console.print(
            f"[bold]fastapi-repl[/] {__version__} on Python {sys.version.split()[0]}"
        )
        loaded = _load(config_file, env_file=env_file, lifespan=lifespan)
        console.print(f"[bold]Project root:[/] {loaded.root}")
        files = ", ".join(str(f) for f in loaded.files) or "none (using defaults)"
        console.print(f"[bold]Config files:[/] {files}")
        for warning in loaded.warnings:
            problems += 1
            console.print(f"  [yellow]![/] {escape(warning)}")

        console.print("\n[bold]Interfaces[/]")
        config = loaded.config
        try:
            selected = select_interface(config.interface, config.interface_order).name
        except ReplError as exc:
            problems += 1
            selected = None
            console.print(f"  [red]✗[/] {escape(str(exc))}")
        for name, cls in INTERFACES.items():
            if cls.is_available():
                mark = "[green]✓[/]"
                note = " [bold](selected)[/]" if name == selected else ""
                console.print(f"  {mark} {cls.describe()}{note}")
            else:
                console.print(
                    f"  [dim]- {cls.display_name}: not installed ({escape(cls.install_hint())})[/]"
                )

        console.print("\n[bold]Adapters[/]")
        for name, adapter_path in available_adapters().items():
            try:
                cls = load_adapter_class(adapter_path)
            except Exception as exc:
                problems += 1
                console.print(f"  [red]✗[/] {name}: {escape(str(exc))}")
                continue
            if cls.is_installed():
                console.print(
                    f"  [green]✓[/] {cls.display_name or name} {cls.version() or ''}"
                )
            else:
                console.print(f"  [dim]- {cls.display_name or name}: not installed[/]")

        console.print("\n[bold]Loading the project[/]")
        try:
            session = _start_session(loaded, show_status=True)
        except ReplError as exc:
            console.print(f"  [red]✗[/] {escape(str(exc))}")
            raise typer.Exit(1) from None
        except Exception as exc:
            console.print(f"  [red]✗[/] {type(exc).__name__}: {escape(str(exc))}")
            _print_user_traceback(exc)
            raise typer.Exit(1) from None
        try:
            for adapter in session.adapters:
                console.print(f"  [green]✓[/] adapter: {adapter.describe()}")
                database = adapter.database()
                if database:
                    mode = " (read-only)" if loaded.config.read_only else ""
                    console.print(f"  [green]✓[/] database: {escape(database)}{mode}")
            if not session.adapters:
                console.print(
                    "  [yellow]![/] no ORM adapter detected (set 'models' or 'adapters')"
                )
            counts = {g: len(e) for g, e in session.namespace.by_group().items()}
            summary = ", ".join(
                f"{n} {g}" for g, n in counts.items() if g != "builtins"
            )
            console.print(f"  [green]✓[/] loaded {summary or 'nothing'}")
            for message in session.warnings:
                problems += 1
                console.print(f"  [yellow]![/] {escape(message)}")
            for failure in session.namespace.failures:
                problems += 1
                console.print(
                    f"  [red]✗[/] {escape(failure.what)}: {escape(failure.message)}"
                )
                err_console.print(
                    "".join(traceback.format_exception(failure.error)).rstrip(),
                    style="dim",
                    highlight=False,
                    markup=False,
                )
        finally:
            session.close()

        if problems:
            console.print(f"\n[yellow]{problems} problem(s) found.[/]")
            raise typer.Exit(1)
        console.print("\n[green]Everything looks good.[/]")


def main() -> None:
    """Console script entry point."""
    app()


__all__ = ["app", "main"]
