"""Exceptions raised by fastapi-repl."""

from __future__ import annotations


class ReplError(Exception):
    """Base class for all fastapi-repl errors.

    The CLI catches these and prints the message without a traceback, so the
    message should tell the user what went wrong and how to fix it.
    """


class ConfigError(ReplError):
    """The configuration is invalid or could not be read."""


class ImportSpecError(ReplError):
    """An import spec (``imports``, ``objects``, ``base``...) is malformed."""


class CollisionError(ReplError):
    """Two models want the same name and ``collision = "error"`` is set."""


class LifespanError(ReplError):
    """The application's ASGI lifespan startup or shutdown failed."""


class InterfaceUnavailableError(ReplError):
    """The requested interactive interface is not installed."""
