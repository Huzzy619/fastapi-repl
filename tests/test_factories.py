from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from fastapi_repl import ReplError, build_namespace

MODULE = """
EVENTS = []


def sync_dep():
    try:
        yield "sync-value"
        EVENTS.append("sync-after-yield")
    finally:
        EVENTS.append("sync-finally")


async def async_dep():
    try:
        yield "async-value"
        EVENTS.append("async-after-yield")
    finally:
        EVENTS.append("async-finally")


async def empty():
    return
    yield
"""


@pytest.fixture
def factories_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    (tmp_path / "factories_mod.py").write_text(MODULE)
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    sys.modules.pop("factories_mod", None)


def _write_config(root: Path, body: str) -> None:
    (root / "fastapi-repl.toml").write_text(body)


def test_generator_factories_yield_their_value_and_close_on_exit(factories_project: Path) -> None:
    _write_config(
        factories_project,
        'imports = ["factories_mod:sync_dep()"]\n\n[objects]\nconn = "factories_mod:async_dep()"\n',
    )
    session, ns = build_namespace()
    try:
        assert ns["sync_dep"] == "sync-value"
        assert ns["conn"] == "async-value"
        events = sys.modules["factories_mod"].EVENTS
        assert events == []
    finally:
        session.close()
    # Closed in reverse order; code after `yield` (e.g. a commit) never runs.
    assert events == ["async-finally", "sync-finally"]


def test_generator_that_yields_nothing_is_an_error(factories_project: Path) -> None:
    _write_config(
        factories_project, 'strict = true\n\n[objects]\nnothing = "factories_mod:empty()"\n'
    )
    with pytest.raises(ReplError, match="did not yield a value"):
        build_namespace()
