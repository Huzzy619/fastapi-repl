from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi_repl.config import load_config
from fastapi_repl.init_project import detect_project, render_toml


def make_project(root: Path) -> Path:
    (root / "app" / "db").mkdir(parents=True)
    (root / "app" / "models").mkdir()
    for pkg in ("app", "app/db", "app/models"):
        (root / pkg / "__init__.py").write_text("")
    (root / "app" / "db" / "session.py").write_text(
        "from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker\n"
        "from sqlalchemy.orm import DeclarativeBase\n"
        "engine = create_async_engine('sqlite+aiosqlite://')\n"
        "SessionLocal = async_sessionmaker(engine)\n"
        "class Base(DeclarativeBase):\n    pass\n"
    )
    (root / "app" / "models" / "user.py").write_text("from sqlalchemy import Column\n")
    (root / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    (root / "tests").mkdir()
    (root / "tests" / "models.py").write_text("# ignored\n")
    (root / ".env").write_text("X=1\n")
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\nversion = '0'\n")
    return root


def test_detect_project(tmp_path: Path) -> None:
    detection = detect_project(make_project(tmp_path))
    assert detection.orms == ["sqlalchemy"]
    assert detection.app == "app.main:app"
    assert detection.models == ["app.models"]
    assert detection.base == "app.db.session:Base"
    assert detection.engine == "app.db.session:engine"
    assert detection.session_factory == "app.db.session:SessionLocal"
    assert detection.env_file == ".env"


def test_src_layout(tmp_path: Path) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    (tmp_path / "src" / "pkg" / "models.py").write_text("from tortoise import fields\n")
    (tmp_path / "src" / "pkg" / "db.py").write_text("TORTOISE_ORM = {}\n")
    detection = detect_project(tmp_path)
    assert detection.pythonpath == ["src"]
    assert detection.models == ["pkg.models"]
    assert detection.orms == ["tortoise"]
    assert detection.to_config()["tortoise"] == {"config": "pkg.db:TORTOISE_ORM"}


def test_rendered_toml_is_valid_config(tmp_path: Path) -> None:
    detection = detect_project(make_project(tmp_path))
    text = render_toml(detection.to_config(), header="tool.fastapi-repl")
    data = tomllib.loads(text)["tool"]["fastapi-repl"]
    assert data["sqlalchemy"]["engine"] == "app.db.session:engine"
    standalone = render_toml(detection.to_config(), header=None)
    (tmp_path / "fastapi-repl.toml").write_text(standalone)
    config = load_config(cwd=tmp_path, environ={}).config
    assert config.models == ["app.models"]


def test_init_writes_pyproject(tmp_path: Path, monkeypatch, invoke) -> None:
    make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = invoke("init")
    assert result.exit_code == 0, result.output
    data = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    assert data["project"]["name"] == "demo"
    assert data["tool"]["fastapi-repl"]["app"] == "app.main:app"

    again = invoke("init")
    assert again.exit_code == 1
    assert "already has" in again.stderr


def test_init_standalone_and_force(tmp_path: Path, monkeypatch, invoke) -> None:
    make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert invoke("init", "--standalone").exit_code == 0
    assert (tmp_path / "fastapi-repl.toml").is_file()
    assert invoke("init", "--standalone").exit_code == 1
    assert invoke("init", "--standalone", "--force").exit_code == 0


def test_init_dry_run_writes_nothing(tmp_path: Path, monkeypatch, invoke) -> None:
    make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = (tmp_path / "pyproject.toml").read_text()
    result = invoke("init", "--dry-run")
    assert result.exit_code == 0
    assert "[tool.fastapi-repl]" in result.stdout
    assert (tmp_path / "pyproject.toml").read_text() == before


def test_fastapi_entrypoint_is_not_repeated(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.fastapi]\nentrypoint = "app.main:app"\n')
    detection = detect_project(tmp_path)
    assert detection.app == "app.main:app"
    assert "app" not in detection.to_config()
