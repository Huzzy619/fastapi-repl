"""Python API: start a shell from your own code."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from fastapi_repl.banner import render_banner, render_notes
from fastapi_repl.config import LoadedConfig, load_config
from fastapi_repl.errors import ReplError
from fastapi_repl.interfaces import InterfaceContext, select_interface
from fastapi_repl.session import ReplSession


def embed(
    namespace: dict[str, Any] | None = None,
    *,
    interface: str | None = None,
    config_file: str | Path | None = None,
    include_caller: bool = True,
    banner: bool = True,
    **overrides: Any,
) -> None:
    """Open a fastapi-repl shell right here, like ``IPython.embed()``.

    The project configuration is discovered as usual, then the caller's local
    and global variables (and ``namespace``) are added on top, so you can poke
    at the state of a script or a debugging session with your models and
    session at hand.

    Args:
        namespace: Extra names to add last.
        interface: ``"ipython"``, ``"ptpython"``, ``"python"``... Defaults to the config.
        config_file: Use this config file instead of discovering one.
        include_caller: Add the caller's globals and locals.
        banner: Print the startup banner.
        **overrides: Any :class:`~fastapi_repl.config.ReplConfig` setting,
            e.g. ``print_sql=True``.

    Raises:
        ReplError: If called while an event loop is running (for example
            inside an ``async def`` endpoint). The shell needs to own the loop.

    Example:
        ```python
        from fastapi_repl import embed

        def debug_user(user_id: int) -> None:
            user = load_user(user_id)
            embed()  # `user`, `user_id`, your models and `session` are available
        ```
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise ReplError(
            "embed() cannot run inside a running event loop. Call it from synchronous code."
        )

    extra: dict[str, Any] = {}
    if include_caller:
        frame = sys._getframe(1)
        extra.update(frame.f_globals)
        extra.update(frame.f_locals)
        for dunder in ("__name__", "__file__", "__builtins__", "__spec__", "__loader__"):
            extra.pop(dunder, None)
    if namespace:
        extra.update(namespace)
    if interface is not None:
        overrides["interface"] = interface

    loaded = load_config(cli=overrides, config_file=config_file)
    start_shell(loaded, extra=extra, banner=banner)


def start_shell(
    loaded: LoadedConfig,
    *,
    extra: dict[str, Any] | None = None,
    banner: bool = True,
    console: Console | None = None,
) -> None:
    """Build a session from ``loaded`` and run the configured interface until exit."""
    console = console or Console()
    config = loaded.config
    interface_cls = select_interface(config.interface, config.interface_order)
    with ReplSession(loaded, console=console, extra=extra) as session:
        assert session.runtime is not None
        if banner and not config.quiet:
            render_banner(session, interface_cls, console=console)
        else:
            render_notes(session, console=console)
        context = InterfaceContext(
            namespace=session.namespace.to_dict(),
            runtime=session.runtime,
            loaded=loaded,
            console=console,
        )
        interface_cls(context).start()


def build_namespace(
    config_file: str | Path | None = None, **overrides: Any
) -> tuple[ReplSession, dict[str, Any]]:
    """Build a session without starting a shell.

    Useful in notebooks, tests and scripts. Remember to call
    ``session.close()`` (or use the session as a context manager) when done.

    Example:
        ```python
        session, ns = build_namespace(print_sql=True)
        try:
            users = session.runtime.run(ns["session"].scalars(ns["select"](ns["User"])))
        finally:
            session.close()
        ```
    """
    loaded = load_config(cli=overrides, config_file=config_file)
    session = ReplSession(loaded)
    session.start()
    return session, session.namespace.to_dict()
