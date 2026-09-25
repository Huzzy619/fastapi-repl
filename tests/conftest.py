from __future__ import annotations

import gc
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fastapi_repl.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_PACKAGES = ("sa_async_app", "sa_sync_app", "sqlmodel_app", "tortoise_app", "plugin_app")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(os.environ):
        if name.startswith("FASTAPI_REPL_"):
            monkeypatch.delenv(name)
    yield
    for name in list(sys.modules):
        if name.split(".")[0] in FIXTURE_PACKAGES:
            del sys.modules[name]
    gc.collect()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], Path]:
    """Copy a fixture project to a temp dir and chdir into it."""

    def make(name: str) -> Path:
        target = tmp_path / name
        shutil.copytree(FIXTURES / name, target)
        monkeypatch.chdir(target)
        return target

    return make


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def invoke(runner: CliRunner):
    def run(*args: str, input: str | None = None):
        return runner.invoke(app, list(args), input=input, catch_exceptions=False)

    return run


def run_cli(args: list[str], cwd: Path, input: str | None = None) -> subprocess.CompletedProcess:
    """Run fastapi-repl in a subprocess (for isolation from global ORM state)."""
    return subprocess.run(
        [sys.executable, "-m", "fastapi_repl", *args],
        cwd=cwd,
        input=input,
        capture_output=True,
        text=True,
        timeout=120,
    )
