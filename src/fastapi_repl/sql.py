"""Pretty-printing of SQL statements for ``--print-sql``."""

from __future__ import annotations

import os
import sys
import sysconfig
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text

_PACKAGE_DIR = str(Path(__file__).resolve().parent)
_LIBRARY_DIRS = tuple(
    {
        str(Path(p).resolve())
        for p in (
            sysconfig.get_paths().get("stdlib"),
            sysconfig.get_paths().get("purelib"),
            sysconfig.get_paths().get("platlib"),
        )
        if p
    }
)


def _is_library_frame(filename: str) -> bool:
    if filename.startswith(("<frozen", "<string>")):
        return True
    try:
        path = str(Path(filename).resolve())
    except (OSError, ValueError):
        return False
    return path.startswith(_PACKAGE_DIR) or path.startswith(_LIBRARY_DIRS)


def find_caller(stack: Sequence[traceback.FrameSummary] | None = None) -> str | None:
    """Return ``file:line`` of the innermost frame that belongs to user code."""
    frames = stack if stack is not None else traceback.extract_stack()
    for frame in reversed(frames):
        if not _is_library_frame(frame.filename):
            filename = frame.filename
            if os.path.isabs(filename):
                with_cwd = os.path.relpath(filename)
                filename = with_cwd if not with_cwd.startswith("..") else filename
            return f"{filename}:{frame.lineno}"
    return None


class SQLPrinter:
    """Prints SQL statements with syntax highlighting.

    Adapters call the printer with each statement they see. Custom adapters
    can use it too; see "Writing adapters" in the docs.

    Args:
        console: Where to print. Defaults to stderr, so piped output stays clean.
        truncate: Maximum number of characters of SQL to show.
        location: Also show the line of user code that triggered the query.
    """

    def __init__(
        self,
        console: Console | None = None,
        *,
        truncate: int | None = None,
        location: bool = False,
    ) -> None:
        self.console = console or Console(stderr=True)
        self.truncate = truncate
        self.location = location

    def format_statement(self, statement: str) -> str:
        statement = statement.strip()
        if self.truncate is not None and len(statement) > self.truncate:
            statement = statement[: self.truncate] + "…"
        return statement

    def __call__(
        self,
        statement: str,
        params: Any = None,
        *,
        duration: float | None = None,
        many: bool = False,
        caller: str | None = None,
    ) -> None:
        """Print one statement.

        Args:
            statement: The SQL text.
            params: Bound parameters, shown dimmed.
            duration: Execution time in seconds.
            many: The statement ran with ``executemany``.
            caller: ``file:line`` to show when ``location`` is enabled. Found
                automatically when omitted.
        """
        self.console.print(
            Syntax(self.format_statement(statement), "sql", theme="ansi_dark", word_wrap=True)
        )
        meta = Text(style="dim")
        if params:
            rendered = params if isinstance(params, str) else repr(params)
            if many and isinstance(params, list) and len(params) > 1:
                rendered = f"{len(params)} parameter sets"
            elif len(rendered) > 300:
                rendered = rendered[:300] + "…"
            meta.append(f"params: {rendered}")
        if duration is not None:
            if meta:
                meta.append("  ")
            meta.append(f"{duration * 1000:.2f} ms")
        if self.location:
            where = caller or find_caller()
            if where:
                if meta:
                    meta.append("  ")
                meta.append(f"at {where}")
        if meta:
            self.console.print(meta)
        if sys.stderr is not None:
            self.console.file.flush()
