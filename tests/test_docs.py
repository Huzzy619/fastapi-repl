"""Keep the documentation honest.

- Every TOML example with a ``[tool.fastapi-repl`` table must be a valid config.
- Python examples preceded by ``<!-- test: <fixture> -->`` must run in that fixture.
- Every setting must be documented in ``docs/configuration.md``.
- ``docs/cli.md`` must match the current CLI.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel
from tests.conftest import FIXTURES, run_cli

from fastapi_repl.config import (
    HooksOptions,
    ReplConfig,
    SQLAlchemyOptions,
    TortoiseOptions,
    load_config,
)

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
PAGES = sorted([ROOT / "README.md", *DOCS.rglob("*.md")])

FENCE = re.compile(
    r"(?:<!-- test: (?P<fixture>[\w-]+) -->\n)?^```(?P<lang>\w+)[^\n]*\n(?P<body>.*?)^```",
    re.MULTILINE | re.DOTALL,
)


def _blocks(lang: str) -> list[tuple[str, str, str | None]]:
    found = []
    for page in PAGES:
        text = page.read_text()
        for match in FENCE.finditer(text):
            if match["lang"] == lang:
                line = text.count("\n", 0, match.start()) + 1
                found.append((f"{page.relative_to(ROOT)}:{line}", match["body"], match["fixture"]))
    return found


TOML_EXAMPLES = [
    (where, body) for where, body, _ in _blocks("toml") if "[tool.fastapi-repl" in body
]
PYTHON_EXAMPLES = [(where, body, fixture) for where, body, fixture in _blocks("python") if fixture]


def test_examples_were_found() -> None:
    assert len(TOML_EXAMPLES) > 10
    assert len(PYTHON_EXAMPLES) >= 3


@pytest.mark.parametrize(("where", "body"), TOML_EXAMPLES, ids=[w for w, _ in TOML_EXAMPLES])
def test_toml_example_is_valid_config(where: str, body: str, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(body)
    loaded = load_config(cwd=tmp_path, environ={}, load_env_file=False)
    assert loaded.files, where


@pytest.mark.parametrize(
    ("where", "body", "fixture"), PYTHON_EXAMPLES, ids=[w for w, _, _ in PYTHON_EXAMPLES]
)
def test_python_example_runs(where: str, body: str, fixture: str, tmp_path: Path) -> None:
    target = tmp_path / fixture
    shutil.copytree(FIXTURES / fixture, target)
    result = run_cli(["-q", "-c", body], cwd=target)
    assert result.returncode == 0, f"{where}\n{result.stdout}\n{result.stderr}"


def _fields(model: type[BaseModel]) -> list[str]:
    return list(model.model_fields)


def test_every_setting_is_documented() -> None:
    text = (DOCS / "configuration.md").read_text()
    missing = [name for name in _fields(ReplConfig) if f"### `{name}`" not in text]
    for model in (SQLAlchemyOptions, TortoiseOptions, HooksOptions):
        missing += [f"{model.__name__}.{n}" for n in _fields(model) if f"| `{n}`" not in text]
    assert not missing, f"Undocumented settings in docs/configuration.md: {missing}"


def test_cli_reference_is_up_to_date(tmp_path: Path) -> None:
    output = tmp_path / "cli.md"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "typer",
            "fastapi_repl.cli",
            "utils",
            "docs",
            "--name",
            "fastapi-repl",
            "--title",
            "CLI reference",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        env={**os.environ, "COLUMNS": "100", "TERM": "dumb"},
    )
    assert output.read_text() == (DOCS / "cli.md").read_text(), (
        "docs/cli.md is stale. Regenerate it with the command in CONTRIBUTING.md."
    )
