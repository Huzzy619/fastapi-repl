"""Interactive interfaces and the logic that picks one."""

from __future__ import annotations

from collections.abc import Iterable

from fastapi_repl.errors import ConfigError, InterfaceUnavailableError
from fastapi_repl.interfaces.base import Interface, InterfaceContext
from fastapi_repl.interfaces.bpython import BpythonInterface
from fastapi_repl.interfaces.ipython import IPythonInterface
from fastapi_repl.interfaces.ptpython import PtipythonInterface, PtpythonInterface
from fastapi_repl.interfaces.python import AsyncConsole, PythonInterface

INTERFACES: dict[str, type[Interface]] = {
    cls.name: cls
    for cls in (
        IPythonInterface,
        PtpythonInterface,
        PtipythonInterface,
        BpythonInterface,
        PythonInterface,
    )
}

__all__ = [
    "INTERFACES",
    "AsyncConsole",
    "Interface",
    "InterfaceContext",
    "select_interface",
]


def select_interface(name: str, order: Iterable[str]) -> type[Interface]:
    """Return the interface class to use.

    Args:
        name: A specific interface, or ``"auto"``.
        order: Preference order for ``"auto"``. The plain Python shell is
            always the last resort.

    Raises:
        InterfaceUnavailableError: If a specific interface is not installed.
        ConfigError: If the name is unknown.
    """
    if name != "auto":
        cls = INTERFACES.get(name)
        if cls is None:
            raise ConfigError(
                f"Unknown interface '{name}'. Choose one of: {', '.join(INTERFACES)}."
            )
        if not cls.is_available():
            raise InterfaceUnavailableError(
                f"{cls.display_name} is not installed. Install it with: {cls.install_hint()}"
            )
        return cls
    for candidate in order:
        cls = INTERFACES.get(candidate)
        if cls is None:
            raise ConfigError(f"Unknown interface '{candidate}' in interface_order.")
        if cls.is_available():
            return cls
    return PythonInterface
