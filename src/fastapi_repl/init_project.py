"""``fastapi-repl init``: detect the project layout and write a starter config.

Detection is purely textual (regular expressions over your source files); no
project code is imported, so it is safe to run on any project.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git",
    ".hg",
    ".venv",
    "venv",
    "env",
    ".tox",
    ".nox",
    "node_modules",
    "__pycache__",
    "site-packages",
    "build",
    "dist",
    "migrations",
    "alembic",
    "tests",
    "test",
    "docs",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
MAX_FILES = 3000

_ASSIGN = r"^(?P<name>[A-Za-z_]\w*)\s*(?::[^=\n]+)?=\s*"
PATTERNS = {
    "async_engine": re.compile(_ASSIGN + r"(?:\w+\.)?create_async_engine\(", re.M),
    "engine": re.compile(_ASSIGN + r"(?:\w+\.)?create_engine\(", re.M),
    "session_factory": re.compile(
        _ASSIGN + r"(?:\w+\.)?(?:async_sessionmaker|sessionmaker)\(", re.M
    ),
    "base_class": re.compile(
        r"^class (?P<name>[A-Za-z_]\w*)\([^)]*\b(?:DeclarativeBase|DeclarativeBaseNoMeta)\b", re.M
    ),
    "base_factory": re.compile(_ASSIGN + r"(?:\w+\.)?declarative_base\(", re.M),
    "app": re.compile(_ASSIGN + r"(?:FastAPI|Starlette|Litestar)\(", re.M),
    "tortoise_config": re.compile(r"^(?P<name>TORTOISE_ORM|TORTOISE_CONFIG)\s*=", re.M),
}
USES = {
    "sqlmodel": re.compile(r"^\s*(?:from|import)\s+sqlmodel\b", re.M),
    "sqlalchemy": re.compile(r"^\s*(?:from|import)\s+sqlalchemy\b", re.M),
    "tortoise": re.compile(r"^\s*(?:from|import)\s+tortoise\b", re.M),
}


@dataclass
class Detection:
    """What ``init`` found. Every field is optional."""

    root: Path
    pythonpath: list[str] = field(default_factory=list)
    app: str | None = None
    app_from_fastapi_cli: bool = False
    orms: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    base: str | None = None
    engine: str | None = None
    session_factory: str | None = None
    tortoise_config: str | None = None
    env_file: str | None = None

    def to_config(self) -> dict[str, Any]:
        """Render the detection as a ``[tool.fastapi-repl]`` table."""
        table: dict[str, Any] = {}
        if self.app and not self.app_from_fastapi_cli:
            table["app"] = self.app
        if self.pythonpath and self.pythonpath != ["."]:
            table["pythonpath"] = self.pythonpath
        if self.env_file:
            table["env_file"] = self.env_file
        if self.models:
            table["models"] = self.models
        if self.base:
            table["base"] = self.base
        table["imports"] = []
        sqlalchemy: dict[str, Any] = {}
        if self.engine:
            sqlalchemy["engine"] = self.engine
        if self.session_factory:
            sqlalchemy["session_factory"] = self.session_factory
        if sqlalchemy:
            table["sqlalchemy"] = sqlalchemy
        if self.tortoise_config:
            table["tortoise"] = {"config": self.tortoise_config}
        return table


def _iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                files.append(Path(dirpath) / filename)
                if len(files) >= MAX_FILES:
                    return files
    return files


def _module_name(path: Path, root: Path, source_roots: list[Path]) -> str | None:
    for source_root in source_roots:
        try:
            rel = path.relative_to(source_root)
        except ValueError:
            continue
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if all(p.isidentifier() for p in parts) and parts:
            return ".".join(parts)
    return None


def detect_project(root: Path) -> Detection:
    """Scan ``root`` and guess the configuration."""
    root = root.resolve()
    detection = Detection(root=root)
    source_roots = [root / "src", root] if (root / "src").is_dir() else [root]
    if (root / "src").is_dir():
        detection.pythonpath = ["src"]

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            data = {}
        entrypoint = data.get("tool", {}).get("fastapi", {}).get("entrypoint")
        if isinstance(entrypoint, str):
            detection.app = entrypoint
            detection.app_from_fastapi_cli = True

    if (root / ".env").is_file():
        detection.env_file = ".env"

    found: dict[str, list[str]] = {key: [] for key in PATTERNS}
    uses: set[str] = set()
    model_modules: list[str] = []
    for path in _iter_python_files(root):
        module = _module_name(path, root, source_roots)
        if module is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for orm, pattern in USES.items():
            if pattern.search(text):
                uses.add(orm)
        for key, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                found[key].append(f"{module}:{match.group('name')}")
        last = module.split(".")[-1]
        if last == "models":
            model_modules.append(module)

    if "sqlmodel" in uses:
        detection.orms.append("sqlmodel")
    elif "sqlalchemy" in uses:
        detection.orms.append("sqlalchemy")
    if "tortoise" in uses:
        detection.orms.append("tortoise")

    # Keep only the outermost "models" packages/modules.
    model_modules.sort(key=lambda m: (m.count("."), m))
    for module in model_modules:
        if not any(module.startswith(existing + ".") for existing in detection.models):
            detection.models.append(module)

    detection.base = _first(found["base_class"]) or _first(found["base_factory"])
    detection.engine = _first(found["async_engine"]) or _first(found["engine"])
    detection.session_factory = _first(found["session_factory"])
    detection.tortoise_config = _first(found["tortoise_config"])
    if detection.app is None:
        detection.app = _first(found["app"])
    return detection


def _first(values: list[str]) -> str | None:
    return sorted(values, key=lambda v: (v.count("."), v))[0] if values else None


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"Cannot render {value!r} as TOML")


def render_toml(table: dict[str, Any], *, header: str | None) -> str:
    """Render a config table. ``header`` is e.g. ``tool.fastapi-repl`` or None for a bare file."""
    lines: list[str] = []
    scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
    sections = {k: v for k, v in table.items() if isinstance(v, dict)}
    if header:
        lines.append(f"[{header}]")
    comments = {
        "imports": '# Extra names, e.g. "from app.core.config import settings"',
    }
    for key, value in scalars.items():
        if key in comments:
            lines.append(comments[key])
        lines.append(f"{key} = {_toml_value(value)}")
    for name, section in sections.items():
        lines.append("")
        lines.append(f"[{header}.{name}]" if header else f"[{name}]")
        for key, value in section.items():
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"
