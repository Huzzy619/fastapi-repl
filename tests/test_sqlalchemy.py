from __future__ import annotations

import json
import sys

import pytest
from tests.conftest import run_cli

from fastapi_repl.config import load_config
from fastapi_repl.session import ReplSession


def test_async_project_namespace(project) -> None:
    project("sa_async")
    with ReplSession(load_config()) as session:
        ns = session.namespace.to_dict()
        assert {"User", "Post", "Tag", "legacy_Tag"} <= set(ns)
        assert type(ns["session"]).__name__ == "AsyncSession"
        assert type(ns["engine"]).__name__ == "AsyncEngine"
        assert ns["settings"].app_name == "sa-async-fixture"
        assert {"select", "func", "selectinload", "AsyncSession"} <= set(ns)
        assert [a.name for a in session.adapters] == ["sqlalchemy"]
        assert session.adapters[0].describe().endswith("(async)")
        assert not session.namespace.failures


def test_async_queries_share_one_loop(project, invoke) -> None:
    project("sa_async")
    code = (
        "users = (await session.scalars(select(User).order_by(User.name))).all()\n"
        "print([u.name for u in users])\n"
        "post = (await session.scalars(select(Post).options(selectinload(Post.author)))).one()\n"
        "print(post.author.name)\n"
    )
    result = invoke("-c", code)
    assert result.exit_code == 0, result.output
    assert "['ada', 'grace']" in result.stdout
    assert "ada" in result.stdout.splitlines()[-1]


def test_async_lifespan(project, invoke) -> None:
    project("sa_async")
    code = "from sa_async_app.main import EVENTS\nprint(EVENTS, lifespan_state['greeting'])\n"
    result = invoke("--lifespan", "-c", code)
    assert result.exit_code == 0, result.output
    assert "['startup'] hello from lifespan" in result.stdout
    from sa_async_app.main import EVENTS

    assert EVENTS == ["startup", "shutdown"]


def test_print_sql(project, invoke) -> None:
    project("sa_async")
    result = invoke(
        "--print-sql",
        "--truncate-sql",
        "20",
        "-c",
        "await session.scalar(select(func.count(User.id)))",
    )
    assert result.exit_code == 0, result.output
    assert "SELECT count(users.i…" in result.stderr
    assert "ms" in result.stderr
    # SQL from the startup hook is not printed.
    assert "CREATE TABLE" not in result.stderr


def test_dont_load_and_aliases(project, invoke) -> None:
    project("sa_async")
    result = invoke("imports", "--json", "--dont-load", "sa_async_app.models.legacy")
    names = {n["name"] for n in json.loads(result.stdout)["names"]}
    assert "legacy_Tag" not in names
    assert "Tag" in names

    result = invoke("imports", "--json", "-x", "Tag", "-x", "Po*")
    names = {n["name"] for n in json.loads(result.stdout)["names"]}
    assert not {"Tag", "legacy_Tag", "Post"} & names
    assert "User" in names


def test_model_aliases(project, invoke) -> None:
    root = project("sa_async")
    with (root / "pyproject.toml").open("a") as fh:
        fh.write(
            '\n[tool.fastapi-repl.model_aliases]\n"sa_async_app.models.legacy.Tag" = "OldTag"\n'
        )
    result = invoke("imports", "--json")
    names = {n["name"] for n in json.loads(result.stdout)["names"]}
    assert {"Tag", "OldTag"} <= names
    assert "legacy_Tag" not in names


def test_collision_error_strategy(project, invoke, monkeypatch) -> None:
    project("sa_async")
    monkeypatch.setenv("FASTAPI_REPL_COLLISION", "error")
    result = invoke("-c", "pass")
    assert result.exit_code == 1
    assert "Two models are both called 'Tag'" in result.stderr


def test_models_found_from_base_registry_only(project, invoke) -> None:
    root = project("sa_async")
    text = (
        (root / "pyproject.toml")
        .read_text()
        .replace(
            'models = ["sa_async_app.models"]\n', 'pre_imports = ["import sa_async_app.models"]\n'
        )
    )
    (root / "pyproject.toml").write_text(text)
    result = invoke("imports", "--json")
    names = {n["name"] for n in json.loads(result.stdout)["names"]}
    # Nothing is scanned, but every imported class mapped on Base's registry is found.
    # models/legacy.py is never imported, so its Tag is not there.
    assert {"User", "Post", "Tag"} <= names
    assert "legacy_Tag" not in names


def test_session_closed_and_engine_disposed(project) -> None:
    project("sa_async")
    session = ReplSession(load_config())
    session.start()
    adapter = session.adapters[0]
    assert adapter.session is not None
    session.close()
    assert adapter.session is None
    assert session.runtime is not None and session.runtime.closed


def test_sync_project_autodetects_engine() -> None:
    # Run in a subprocess: engine auto-detection looks at every engine in memory.
    import shutil
    import tempfile
    from pathlib import Path

    from tests.conftest import FIXTURES

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "sa_sync"
        shutil.copytree(FIXTURES / "sa_sync", root)
        code = (
            "print(type(engine).__name__, type(session).__name__)\n"
            "print(session.query(Book).count(), book_count(), greeting.text)\n"
            "print('AuditLog' in dir(), json.dumps(1), dt.now().year > 2000)\n"
        )
        result = run_cli(["-c", code], cwd=root)
        assert result.returncode == 0, result.stderr
        lines = result.stdout.splitlines()
        assert lines == ["Engine Session", "3 3 hi", "False 1 True"]


def test_factory_objects_are_closed(project) -> None:
    project("sa_sync")
    loaded = load_config()
    loaded.config.sqlalchemy.engine = "sa_sync_app.models:engine"
    with ReplSession(loaded) as session:
        assert session.namespace.entries["greeting"].created
    from sa_sync_app.helpers import CLOSED

    assert CLOSED == ["greeting"]


@pytest.mark.skipif(sys.platform == "win32", reason="select() on pipes")
def test_stdin_is_executed() -> None:
    import shutil
    import tempfile
    from pathlib import Path

    from tests.conftest import FIXTURES

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "sa_async"
        shutil.copytree(FIXTURES / "sa_async", root)
        result = run_cli(
            [], cwd=root, input="print('n =', await session.scalar(select(func.count(User.id))))"
        )
        assert result.returncode == 0, result.stderr
        assert "n = 2" in result.stdout
