"""The shell namespace: every name the user gets, where it came from, and why.

Names are added in layers. A later layer overrides an earlier one, with one
exception: when two *models* want the same name, the ``collision`` strategy
decides what happens.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi_repl.errors import CollisionError

if TYPE_CHECKING:
    from fastapi_repl.adapters.base import ModelInfo
    from fastapi_repl.config import CollisionStrategy

GROUPS = (
    "builtins",
    "pre_imports",
    "helpers",
    "models",
    "objects",
    "imports",
    "hooks",
    "post_imports",
    "extra",
)
"""Namespace groups in the order they are applied."""

GROUP_TITLES = {
    "builtins": "Shell helpers",
    "pre_imports": "Pre-imports",
    "helpers": "ORM helpers",
    "models": "Models",
    "objects": "Objects",
    "imports": "Imports",
    "hooks": "From hooks",
    "post_imports": "Post-imports",
    "extra": "Extra",
}


@dataclass
class Entry:
    """A single name in the namespace."""

    name: str
    value: Any
    group: str
    source: str
    created: bool = False


@dataclass
class LoadFailure:
    """Something that could not be loaded. Shown in the banner as a warning."""

    what: str
    group: str
    error: BaseException

    @property
    def message(self) -> str:
        return f"{type(self.error).__name__}: {self.error}"


@dataclass
class Namespace:
    """An ordered collection of :class:`Entry` objects plus load failures."""

    collision: CollisionStrategy = "prefix"
    model_aliases: Mapping[str, str] = field(default_factory=dict)
    entries: dict[str, Entry] = field(default_factory=dict)
    failures: list[LoadFailure] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Informational messages, e.g. renamed models."""

    def add(
        self,
        name: str,
        value: Any,
        *,
        group: str,
        source: str,
        created: bool = False,
    ) -> Entry:
        """Add or replace a name."""
        entry = Entry(name, value, group, source, created)
        self.entries.pop(name, None)
        self.entries[name] = entry
        return entry

    def add_model(self, model: ModelInfo) -> Entry | None:
        """Add a model, applying aliases and the collision strategy."""
        name = self.model_aliases.get(model.qualname) or self.model_aliases.get(model.name)
        aliased = name is not None
        name = name or model.name
        existing = self.entries.get(name)
        if existing is not None and existing.group == "models" and existing.value is not model.cls:
            if aliased:
                pass
            elif self.collision == "skip":
                self.notes.append(
                    f"Skipped model {model.qualname}: '{name}' is already {existing.source}."
                )
                return None
            elif self.collision == "error":
                raise CollisionError(
                    f"Two models are both called '{name}': {existing.source} and "
                    f"{model.qualname}. Add one of them to 'model_aliases' or 'dont_load'."
                )
            elif self.collision == "prefix":
                prefixed = f"{model.prefix}_{name}" if model.prefix else model.qualname
                self.notes.append(
                    f"Model {model.qualname} was loaded as '{prefixed}' because "
                    f"'{name}' is already {existing.source}."
                )
                name = prefixed
        elif existing is not None and existing.value is model.cls:
            return existing
        return self.add(name, model.cls, group="models", source=model.qualname)

    def fail(self, what: str, group: str, error: BaseException) -> None:
        self.failures.append(LoadFailure(what, group, error))

    def to_dict(self) -> dict[str, Any]:
        return {name: entry.value for name, entry in self.entries.items()}

    def by_group(self) -> dict[str, list[Entry]]:
        grouped: dict[str, list[Entry]] = {}
        for entry in self.entries.values():
            grouped.setdefault(entry.group, []).append(entry)
        return {g: grouped[g] for g in GROUPS if g in grouped} | {
            g: v for g, v in grouped.items() if g not in GROUPS
        }

    def created_values(self) -> list[Any]:
        """Objects created by factories, in creation order (closed on exit)."""
        return [e.value for e in self.entries.values() if e.created]

    def __contains__(self, name: object) -> bool:
        return name in self.entries

    def __len__(self) -> int:
        return len(self.entries)


def is_excluded(model: ModelInfo, patterns: Iterable[str]) -> bool:
    """Return True if ``model`` matches any ``dont_load`` pattern.

    A pattern matches a model name (``User``), its dotted path
    (``app.models.User``), a module prefix (``app.models.billing``) or a glob
    (``*Log``, ``app.models.audit.*``).
    """
    for pattern in patterns:
        if pattern in (model.name, model.qualname):
            return True
        if model.module == pattern or model.module.startswith(pattern + "."):
            return True
        if model.label and pattern == model.label:
            return True
        if any(ch in pattern for ch in "*?[") and (
            fnmatch.fnmatchcase(model.name, pattern) or fnmatch.fnmatchcase(model.qualname, pattern)
        ):
            return True
    return False
