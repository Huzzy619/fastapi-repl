"""The startup banner and the ``imports`` listing."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fastapi_repl.__about__ import __version__
from fastapi_repl.namespace import GROUP_TITLES, Entry

if TYPE_CHECKING:
    from fastapi_repl.interfaces.base import Interface
    from fastapi_repl.session import ReplSession


def _describe_value(value: Any) -> str:
    if isinstance(value, type):
        return "class"
    kind = type(value).__name__
    if kind == "module":
        return "module"
    if callable(value):
        return "function" if kind in {"function", "builtin_function_or_method"} else kind
    return kind


def _names_line(entries: Sequence[Entry], *, show_types: bool) -> Text:
    text = Text()
    for i, entry in enumerate(entries):
        if i:
            text.append(", ")
        text.append(entry.name, style="bold cyan" if entry.group == "models" else "cyan")
        if show_types:
            text.append(f" ({_describe_value(entry.value)})", style="dim")
    return text


def render_banner(
    session: ReplSession,
    interface: type[Interface] | None,
    *,
    console: Console,
) -> None:
    """Print the startup banner."""
    config = session.config
    grouped = session.namespace.by_group()

    header = Text()
    header.append("fastapi-repl ", style="bold")
    header.append(__version__, style="bold green")
    parts = [f"Python {sys.version.split()[0]}"]
    if interface is not None and interface.name != "python":
        parts.append(interface.describe())
    parts.extend(adapter.describe() for adapter in session.adapters)
    if session.lifespan is not None and session.lifespan.started:
        parts.append("lifespan running")
    header.append("  " + " · ".join(parts), style="dim")

    body: list[Any] = [header, Text(f"Project: {session.root}", style="dim")]

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    for database in _databases(session):
        table.add_row("Database", database)
    for group, entries in grouped.items():
        if group == "builtins":
            continue
        title = GROUP_TITLES.get(group, group)
        label = f"{title} ({len(entries)})" if group == "models" else title
        table.add_row(label, _names_line(entries, show_types=group == "objects"))
    if table.row_count:
        body.append(Text())
        body.append(table)

    tips = list(session.tips())
    if interface is None or interface.supports_await:
        tip_line = Text("Top-level await is on", style="green")
        if tips:
            tip_line.append(", try: ", style="green")
            tip_line.append(tips[0], style="bold")
    else:
        tip_line = Text(
            f"{interface.display_name} has no top-level await; use await_(coroutine).",
            style="yellow",
        )
    body.append(Text())
    body.append(tip_line)
    if config.banner:
        body.append(Text(config.banner))

    console.print(Panel(Group(*body), border_style="blue", expand=False))
    render_notes(session, console=console)
    if config.verbose:
        render_imports(session, console=console)


def _databases(session: ReplSession) -> list[Text]:
    lines = []
    for adapter in session.adapters:
        try:
            database = adapter.database()
        except Exception:
            database = None
        if not database:
            continue
        line = Text(database)
        if session.config.read_only:
            line.append("  read-only", style="bold green")
        lines.append(line)
    return lines


def render_notes(session: ReplSession, *, console: Console) -> None:
    """Print load failures, warnings and collision notes."""
    config = session.config
    for message in session.warnings:
        console.print(f"[yellow]warning:[/] {escape(message)}")
    for note in session.namespace.notes:
        console.print(f"[dim]note: {escape(note)}[/]")
    if session.namespace.failures and not config.quiet_load:
        console.print(f"[yellow]{len(session.namespace.failures)} item(s) could not be loaded:[/]")
        for failure in session.namespace.failures:
            console.print(f"  [yellow]•[/] {escape(failure.what)}: {escape(failure.message)}")
        if not config.verbose:
            console.print("  [dim]Run 'fastapi-repl doctor' for details.[/]")


def render_imports(session: ReplSession, *, console: Console) -> None:
    """Print a table of every name in the namespace and where it came from."""
    table = Table(title="Shell namespace", title_justify="left", expand=False)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Group")
    table.add_column("Type", style="dim")
    table.add_column("Source", style="dim")
    for group, entries in session.namespace.by_group().items():
        for entry in entries:
            table.add_row(
                entry.name,
                GROUP_TITLES.get(group, group),
                _describe_value(entry.value),
                entry.source,
            )
    console.print(table)
