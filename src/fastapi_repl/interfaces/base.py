"""Base class for interactive interfaces."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from rich.console import Console

    from fastapi_repl.config import LoadedConfig
    from fastapi_repl.runtime import Runtime


def private_file(path: Path) -> Path | None:
    """Create ``path`` (and its directory) readable only by the current user.

    History files hold whatever was typed at the prompt, so they must not be
    world-readable. Returns None if the file cannot be created.
    """
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.close(os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600))
        os.chmod(path, 0o600)
    except OSError:
        return None
    return path


@dataclass
class InterfaceContext:
    """What an interface needs to start."""

    namespace: dict[str, Any]
    runtime: Runtime
    loaded: LoadedConfig
    console: Console


class Interface:
    """An interactive shell implementation."""

    name: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    package: ClassVar[str | None] = None
    """Import name that must be installed."""
    distribution: ClassVar[str | None] = None
    """PyPI distribution name, used for the version and install hints."""
    supports_await: ClassVar[bool] = True

    def __init__(self, context: InterfaceContext) -> None:
        self.context = context

    @classmethod
    def is_available(cls) -> bool:
        return cls.package is None or importlib.util.find_spec(cls.package) is not None

    @classmethod
    def version(cls) -> str | None:
        if cls.distribution is None:
            return None
        try:
            return version(cls.distribution)
        except PackageNotFoundError:
            return None

    @classmethod
    def describe(cls) -> str:
        v = cls.version()
        return f"{cls.display_name} {v}" if v else cls.display_name

    @classmethod
    def install_hint(cls) -> str:
        return f"pip install 'fastapi-repl[{cls.name}]'"

    def start(self) -> None:
        """Run the interactive loop until the user exits."""
        raise NotImplementedError
