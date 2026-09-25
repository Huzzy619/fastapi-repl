"""Configuration model and loader.

Settings are merged from several layers. Later layers win:

1. Built-in defaults.
2. ``[tool.fastapi-repl]`` in ``pyproject.toml``.
3. A standalone ``fastapi-repl.toml`` file.
4. ``FASTAPI_REPL_*`` environment variables (including ones from ``env_file``).
5. Command-line flags.

``load_config`` also remembers where every value came from, which powers the
``fastapi-repl config`` command.
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from fastapi_repl.errors import ConfigError

ENV_PREFIX = "FASTAPI_REPL_"
CONFIG_FILENAME = "fastapi-repl.toml"
PYPROJECT_FILENAME = "pyproject.toml"
PYPROJECT_TABLE = "fastapi-repl"

InterfaceName = Literal["auto", "ipython", "ptpython", "ptipython", "bpython", "python"]
CollisionStrategy = Literal["prefix", "skip", "override", "error"]


def _as_list(value: Any) -> Any:
    if isinstance(value, str):
        return [value]
    return value


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class SQLAlchemyOptions(_Section):
    """Options for the SQLAlchemy and SQLModel adapters (``[tool.fastapi-repl.sqlalchemy]``)."""

    engine: str | None = Field(
        default=None,
        description="Import path of your Engine or AsyncEngine, e.g. 'app.db:engine'. "
        "Auto-detected when there is exactly one engine in memory.",
    )
    session_factory: str | None = Field(
        default=None,
        description="Import path of a sessionmaker / async_sessionmaker used to create the "
        "shell session, e.g. 'app.db:SessionLocal'.",
    )
    session: bool = Field(default=True, description="Create a ready-to-use session object.")
    session_name: str = Field(default="session", description="Name of the session in the shell.")
    engine_name: str = Field(default="engine", description="Name of the engine in the shell.")
    dispose_engine: bool = Field(
        default=True, description="Dispose the engine's connection pool when the shell exits."
    )


class TortoiseOptions(_Section):
    """Options for the Tortoise ORM adapter (``[tool.fastapi-repl.tortoise]``)."""

    config: str | None = Field(
        default=None,
        description="Import path of your TORTOISE_ORM config dict, e.g. 'app.db:TORTOISE_ORM'.",
    )
    config_file: str | None = Field(
        default=None,
        description="Path to a Tortoise JSON/YAML config file, relative to the project root.",
    )
    db_url: str | None = Field(
        default=None, description="Database URL, used together with 'modules'."
    )
    modules: dict[str, list[str]] = Field(
        default_factory=dict,
        description="App label to model modules, e.g. {models = ['app.models']}.",
    )
    generate_schemas: bool = Field(
        default=False, description="Create missing tables on startup (handy for SQLite prototypes)."
    )


class HooksOptions(_Section):
    """Callables that customise the shell (``[tool.fastapi-repl.hooks]``)."""

    namespace: list[str] = Field(
        default_factory=list,
        description="Callables (sync or async) returning a dict of extra names. They may "
        "accept one argument: the namespace built so far.",
    )
    startup: list[str] = Field(
        default_factory=list,
        description="Callables run after the namespace is ready (sync or async).",
    )
    shutdown: list[str] = Field(
        default_factory=list,
        description="Callables run when the shell exits (sync or async).",
    )

    _wrap = field_validator("namespace", "startup", "shutdown", mode="before")(_as_list)


class ReplConfig(_Section):
    """The complete fastapi-repl configuration.

    Every field can be set in ``[tool.fastapi-repl]`` (``pyproject.toml``), in
    ``fastapi-repl.toml``, through a ``FASTAPI_REPL_<FIELD>`` environment
    variable, and most of them through a command-line flag.
    """

    # Project
    app: str | None = Field(
        default=None,
        description="Import path of your ASGI app, e.g. 'main:app'. Defaults to "
        "[tool.fastapi] entrypoint. Imported and exposed as `app`.",
    )
    lifespan: bool = Field(
        default=False, description="Run the app's ASGI lifespan (startup/shutdown)."
    )
    pythonpath: list[str] = Field(
        default_factory=lambda: ["."],
        description="Directories (relative to the project root) added to sys.path.",
    )
    env_file: str | None = Field(
        default=None, description="A .env file loaded before your code is imported."
    )

    # Interface
    interface: InterfaceName = Field(default="auto", description="Which interactive shell to use.")
    interface_order: list[str] = Field(
        default_factory=lambda: ["ipython", "ptpython", "bpython", "python"],
        description="Preference order used when interface = 'auto'.",
    )
    startup: bool = Field(
        default=True, description="Run $PYTHONSTARTUP and ~/.pythonrc.py in the plain Python shell."
    )
    ipython_arguments: list[str] = Field(
        default_factory=list, description="Extra command-line arguments passed to IPython."
    )
    jupyter_arguments: list[str] = Field(
        default_factory=list, description="Extra command-line arguments passed to Jupyter."
    )

    # ORM adapters and models
    adapters: list[str] = Field(
        default_factory=list,
        description="Adapters to enable, by name or 'module:Class'. Empty means auto-detect.",
    )
    models: list[str] = Field(
        default_factory=list,
        description="Modules or packages containing your models. Packages are walked recursively.",
    )
    base: list[str] = Field(
        default_factory=list,
        description="Import path(s) of your model base class, e.g. 'app.db:Base'.",
    )
    auto_imports: bool = Field(
        default=True,
        description="Master switch. False gives a bare shell with no automatic imports.",
    )
    load_models: bool = Field(default=True, description="Import every discovered model.")
    dont_load: list[str] = Field(
        default_factory=list,
        description="Models to skip: names, dotted paths, module prefixes or glob patterns.",
    )
    model_aliases: dict[str, str] = Field(
        default_factory=dict,
        description="Rename models: {'User' = 'AuthUser'} or {'app.models.User' = 'AuthUser'}.",
    )
    collision: CollisionStrategy = Field(
        default="prefix",
        description="What to do when two models share a name: prefix, skip, override or error.",
    )
    default_imports: bool = Field(
        default=True, description="Import each adapter's helpers (select, func, Q, F...)."
    )

    # Imports and objects
    pre_imports: list[str] = Field(
        default_factory=list,
        description="Imported first, so models and helpers can override them.",
    )
    imports: list[str] = Field(
        default_factory=list,
        description="Extra imports, e.g. 'from app.core.config import settings'.",
    )
    post_imports: list[str] = Field(
        default_factory=list, description="Imported last, overriding everything else."
    )
    objects: dict[str, str] = Field(
        default_factory=dict,
        description="Named objects: {name = 'module:attr'}. Use 'module:factory()' to call it.",
    )
    hooks: HooksOptions = Field(default_factory=HooksOptions)

    # Adapter options
    sqlalchemy: SQLAlchemyOptions = Field(default_factory=SQLAlchemyOptions)
    tortoise: TortoiseOptions = Field(default_factory=TortoiseOptions)
    plugins: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Options for third-party adapters, keyed by adapter name.",
    )

    # Safety
    read_only: bool = Field(
        default=False,
        description="Open every database connection read-only. The shell refuses to start "
        "if an adapter cannot guarantee it.",
    )
    rollback_on_error: bool = Field(
        default=True,
        description="Roll the session back when a statement leaves it unusable (a failed "
        "flush, or any database error on PostgreSQL).",
    )

    # SQL logging
    print_sql: bool = Field(default=False, description="Print every SQL statement as it runs.")
    truncate_sql: int | None = Field(
        default=None, description="Truncate printed SQL to this many characters."
    )
    print_sql_location: bool = Field(
        default=False, description="Show the line of your code that triggered each query."
    )

    # Output
    quiet: bool = Field(default=False, description="Do not print the startup banner.")
    quiet_load: bool = Field(default=False, description="Do not report import errors.")
    verbose: bool = Field(
        default=False, description="List every loaded name and where it came from."
    )
    strict: bool = Field(default=False, description="Fail instead of warning when an import fails.")
    banner: str | None = Field(
        default=None, description="Extra text shown at the bottom of the banner."
    )

    _wrap = field_validator(
        "pythonpath",
        "models",
        "base",
        "adapters",
        "dont_load",
        "pre_imports",
        "imports",
        "post_imports",
        "interface_order",
        "ipython_arguments",
        "jupyter_arguments",
        mode="before",
    )(_as_list)


SECTION_MODELS: dict[str, type[_Section]] = {
    "hooks": HooksOptions,
    "sqlalchemy": SQLAlchemyOptions,
    "tortoise": TortoiseOptions,
}
"""Fields that are themselves tables with known keys."""

FREEFORM_TABLES = {"objects", "model_aliases", "plugins"}
"""Fields whose keys are user-defined names and must not be normalised."""


@dataclass
class LoadedConfig:
    """The result of :func:`load_config`."""

    config: ReplConfig
    root: Path
    """The project root. Relative paths in the config are resolved from here."""
    files: list[Path] = field(default_factory=list)
    """Config files that were read, lowest precedence first."""
    sources: dict[str, str] = field(default_factory=dict)
    """Maps dotted setting names (``print_sql``, ``sqlalchemy.engine``) to where they came from."""
    warnings: list[str] = field(default_factory=list)

    def source_of(self, key: str) -> str:
        return self.sources.get(key, "default")

    @property
    def config_file(self) -> Path | None:
        """The highest-precedence config file, if any."""
        return self.files[-1] if self.files else None


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc


def _pyproject_table(data: Mapping[str, Any]) -> dict[str, Any] | None:
    tool = data.get("tool", {})
    table = tool.get(PYPROJECT_TABLE)
    if table is None:
        table = tool.get(PYPROJECT_TABLE.replace("-", "_"))
    return table


def find_project_root(start: Path | None = None) -> Path:
    """Find the project root by walking up from ``start`` (default: the cwd).

    The first directory containing ``fastapi-repl.toml``, or a ``pyproject.toml``
    with a ``[tool.fastapi-repl]`` table, wins. Otherwise the nearest directory
    with a ``pyproject.toml`` is used, and failing that ``start`` itself.
    """
    start = (start or Path.cwd()).resolve()
    nearest_pyproject: Path | None = None
    for directory in (start, *start.parents):
        if (directory / CONFIG_FILENAME).is_file():
            return directory
        pyproject = directory / PYPROJECT_FILENAME
        if pyproject.is_file():
            if nearest_pyproject is None:
                nearest_pyproject = directory
            try:
                if _pyproject_table(_read_toml(pyproject)) is not None:
                    return directory
            except ConfigError:
                continue
    return nearest_pyproject or start


def _normalise_keys(table: Mapping[str, Any], *, where: str) -> dict[str, Any]:
    """Accept ``print-sql`` as well as ``print_sql`` for known keys."""
    known = set(ReplConfig.model_fields)
    result: dict[str, Any] = {}
    for key, value in table.items():
        norm = key.replace("-", "_")
        if norm not in known:
            raise ConfigError(
                f"Unknown setting '{key}' in {where}. "
                f"Run 'fastapi-repl config --help' or see the configuration reference."
            )
        if norm in SECTION_MODELS:
            if not isinstance(value, Mapping):
                raise ConfigError(f"'{key}' in {where} must be a table.")
            section_fields = set(SECTION_MODELS[norm].model_fields)
            section: dict[str, Any] = {}
            for sub_key, sub_value in value.items():
                sub_norm = sub_key.replace("-", "_")
                if sub_norm not in section_fields:
                    raise ConfigError(f"Unknown setting '{key}.{sub_key}' in {where}.")
                section[sub_norm] = sub_value
            result[norm] = section
        else:
            result[norm] = value
    return result


def _merge_layer(
    merged: dict[str, Any], sources: dict[str, str], layer: Mapping[str, Any], label: str
) -> None:
    for key, value in layer.items():
        if key in SECTION_MODELS or key in FREEFORM_TABLES:
            target = merged.setdefault(key, {})
            for sub_key, sub_value in value.items():
                target[sub_key] = sub_value
                sources[f"{key}.{sub_key}"] = label
        else:
            merged[key] = value
            sources[key] = label


def _annotation_is_list(annotation: Any) -> bool:
    if get_origin(annotation) is list:
        return True
    return any(get_origin(arg) is list for arg in get_args(annotation))


def _parse_env_value(raw: str, annotation: Any) -> Any:
    stripped = raw.strip()
    if stripped[:1] in "[{":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    if _annotation_is_list(annotation):
        return [part.strip() for part in stripped.split(",") if part.strip()]
    if stripped == "" and type(None) in get_args(annotation):
        return None
    return stripped


def _env_layer(environ: Mapping[str, str], warnings: list[str]) -> tuple[dict[str, Any], dict]:
    """Translate ``FASTAPI_REPL_*`` variables into a config layer.

    Nested settings use a double underscore: ``FASTAPI_REPL_SQLALCHEMY__ENGINE``.
    Lists are comma separated, and JSON is accepted for lists and tables.
    """
    layer: dict[str, Any] = {}
    names: dict[str, str] = {}
    for name, raw in environ.items():
        if not name.startswith(ENV_PREFIX):
            continue
        key = name[len(ENV_PREFIX) :].lower()
        top, _, sub = key.partition("__")
        if top not in ReplConfig.model_fields:
            warnings.append(f"Ignoring unknown environment variable {name}.")
            continue
        if sub:
            if top in SECTION_MODELS:
                section_fields = SECTION_MODELS[top].model_fields
                if sub not in section_fields:
                    warnings.append(f"Ignoring unknown environment variable {name}.")
                    continue
                value = _parse_env_value(raw, section_fields[sub].annotation)
            elif top in FREEFORM_TABLES:
                value = _parse_env_value(raw, str)
                # Freeform keys keep the user's spelling, which env vars cannot express
                # reliably; we use the lower-cased name.
            else:
                warnings.append(f"Ignoring {name}: '{top}' is not a table.")
                continue
            layer.setdefault(top, {})[sub] = value
            names[f"{top}.{sub}"] = name
        else:
            annotation = ReplConfig.model_fields[top].annotation
            value = _parse_env_value(raw, annotation)
            if top in SECTION_MODELS or top in FREEFORM_TABLES:
                if not isinstance(value, dict):
                    warnings.append(f"Ignoring {name}: expected a JSON object.")
                    continue
                if top in SECTION_MODELS:
                    value = _normalise_keys({top: value}, where=f"environment variable {name}")[top]
                for sub_key in value:
                    names[f"{top}.{sub_key}"] = name
            else:
                names[top] = name
            layer[top] = value
    return layer, names


def _format_validation_error(exc: ValidationError, sources: dict[str, str]) -> str:
    lines = ["Invalid fastapi-repl configuration:"]
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"])
        top = str(error["loc"][0]) if error["loc"] else ""
        origin = sources.get(loc) or sources.get(top) or "default"
        lines.append(f"  - {loc}: {error['msg']} (from {origin})")
    return "\n".join(lines)


def load_config(
    *,
    cli: Mapping[str, Any] | None = None,
    config_file: str | Path | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
    load_env_file: bool = True,
) -> LoadedConfig:
    """Discover, merge and validate the configuration.

    Args:
        cli: Values from command-line flags. ``None`` values are ignored.
        config_file: An explicit config file. It may be a ``pyproject.toml``
            (the ``[tool.fastapi-repl]`` table is read) or any other TOML file
            (read as a top-level table, like ``fastapi-repl.toml``).
        cwd: Where to start looking for the project root. Defaults to the cwd.
        environ: Environment variables. Defaults to ``os.environ``.
        load_env_file: Load ``env_file`` into ``os.environ`` before reading
            ``FASTAPI_REPL_*`` variables. Disable in tests.

    Raises:
        ConfigError: If a file cannot be parsed or a value is invalid.
    """
    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}
    files: list[Path] = []
    warnings: list[str] = []

    if config_file is not None:
        path = Path(config_file).expanduser().resolve()
        if not path.is_file():
            raise ConfigError(f"Config file {path} does not exist.")
        root = path.parent
        data = _read_toml(path)
        if path.name == PYPROJECT_FILENAME:
            _apply_fastapi_entrypoint(data, merged, sources, path)
            table = _pyproject_table(data) or {}
            label = f"{path.name} [tool.{PYPROJECT_TABLE}]"
        else:
            table = data
            label = path.name
        _merge_layer(merged, sources, _normalise_keys(table, where=str(path)), label)
        files.append(path)
    else:
        root = find_project_root(cwd)
        pyproject = root / PYPROJECT_FILENAME
        if pyproject.is_file():
            data = _read_toml(pyproject)
            _apply_fastapi_entrypoint(data, merged, sources, pyproject)
            table = _pyproject_table(data)
            if table is not None:
                label = f"{PYPROJECT_FILENAME} [tool.{PYPROJECT_TABLE}]"
                _merge_layer(merged, sources, _normalise_keys(table, where=str(pyproject)), label)
                files.append(pyproject)
        standalone = root / CONFIG_FILENAME
        if standalone.is_file():
            table = _read_toml(standalone)
            _merge_layer(
                merged, sources, _normalise_keys(table, where=str(standalone)), CONFIG_FILENAME
            )
            files.append(standalone)

    cli_layer = {k: v for k, v in (cli or {}).items() if v is not None}
    cli_layer = _normalise_keys(cli_layer, where="command-line flags")

    env = os.environ if environ is None else environ
    env_file = (
        cli_layer.get("env_file") or env.get(f"{ENV_PREFIX}ENV_FILE") or merged.get("env_file")
    )
    if env_file and load_env_file:
        env_path = (root / env_file).resolve()
        if env_path.is_file():
            load_dotenv(env_path, override=False)
        else:
            warnings.append(f"env_file {env_path} does not exist.")

    env_layer, env_names = _env_layer(os.environ if environ is None else environ, warnings)
    for key, value in env_layer.items():
        _merge_layer(merged, sources, {key: value}, "env")
    for key, name in env_names.items():
        sources[key] = f"env {name}"

    _merge_layer(merged, sources, cli_layer, "command line")

    try:
        config = ReplConfig.model_validate(merged)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc, sources)) from None

    return LoadedConfig(config=config, root=root, files=files, sources=sources, warnings=warnings)


def _apply_fastapi_entrypoint(
    data: Mapping[str, Any], merged: dict[str, Any], sources: dict[str, str], path: Path
) -> None:
    """Use FastAPI CLI's ``[tool.fastapi] entrypoint`` as the default ``app``."""
    entrypoint = data.get("tool", {}).get("fastapi", {}).get("entrypoint")
    if isinstance(entrypoint, str) and "app" not in merged:
        merged["app"] = entrypoint
        sources["app"] = f"{path.name} [tool.fastapi] entrypoint"
