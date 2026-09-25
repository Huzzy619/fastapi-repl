"""read_only, rollback_on_error, the database line, and flags reaching Jupyter kernels."""

from __future__ import annotations

import shutil
import stat
import sys

import pytest
from sqlalchemy.exc import OperationalError, PendingRollbackError
from tests.conftest import FIXTURES, run_cli

from fastapi_repl.adapters.base import mask_url
from fastapi_repl.cli import _flags_as_env, _load
from fastapi_repl.config import load_config
from fastapi_repl.interfaces.base import private_file
from fastapi_repl.session import ReplSession


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://app:secret@db:5432/app", "postgresql://app:***@db:5432/app"),
        ("postgresql://app:secret@db/app?sslkey=/k.pem", "postgresql://app:***@db/app"),
        ("postgres://app@db/app", "postgres://app@db/app"),
        ("sqlite://:memory:", "sqlite://:memory:"),
        ("mysql://:pw@db/app", "mysql://:***@db/app"),
    ],
)
def test_mask_url(url: str, expected: str) -> None:
    assert mask_url(url) == expected


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_history_files_are_private(tmp_path) -> None:
    path = private_file(tmp_path / "cache" / "python_history")
    assert path is not None
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def _count_users(session: ReplSession) -> int:
    ns = session.namespace.to_dict()
    assert session.runtime is not None
    query = ns["select"](ns["func"].count()).select_from(ns["User"])
    return session.runtime.run(ns["session"].scalar(query))


def _fail_a_flush(session: ReplSession) -> None:
    ns = session.namespace.to_dict()
    assert session.runtime is not None
    ns["session"].add(ns["User"](name=None))  # name is NOT NULL
    with pytest.raises(Exception, match="NOT NULL"):
        session.runtime.run(ns["session"].flush())


def test_session_is_rolled_back_after_a_failed_flush(project, capsys) -> None:
    project("sa_async")
    with ReplSession(load_config()) as session:
        _fail_a_flush(session)
        assert _count_users(session) == 2
    assert "session was rolled back after the error" in capsys.readouterr().err


def test_rollback_on_error_can_be_turned_off(project) -> None:
    project("sa_async")
    with ReplSession(load_config(cli={"rollback_on_error": False})) as session:
        _fail_a_flush(session)
        with pytest.raises(PendingRollbackError):
            _count_users(session)


def test_read_only_blocks_writes(project) -> None:
    project("sa_sync")
    with ReplSession(load_config()):  # the startup hook creates and fills the tables
        pass
    loaded = load_config(cli={"read_only": True, "hooks": {"startup": []}})
    with ReplSession(loaded) as session:
        ns = session.namespace.to_dict()
        db = ns["session"]
        assert db.scalar(ns["select"](ns["func"].count()).select_from(ns["Book"])) == 3
        db.add(ns["Book"](title="Middlemarch"))
        with pytest.raises(OperationalError, match="readonly"):
            db.commit()
        db.rollback()


def test_read_only_refuses_to_start_when_it_cannot_be_enforced(tmp_path) -> None:
    target = tmp_path / "tortoise_proj"
    shutil.copytree(FIXTURES / "tortoise_proj", target)
    result = run_cli(["--read-only", "-c", "print('should not run')"], cwd=target)
    assert result.returncode == 1
    assert "read_only is on, but it could not be enabled for tortoise" in result.stderr
    assert "should not run" not in result.stdout


def test_doctor_shows_the_database(project, invoke) -> None:
    project("sa_sync")
    result = invoke("doctor")
    assert "database: sqlite:///./sa_sync.db" in result.stdout


def test_command_line_flags_reach_jupyter_kernels(project) -> None:
    project("sa_sync")
    loaded = _load(None, read_only=True, models=["sa_sync_app.models"])
    env = _flags_as_env(loaded)
    assert env == {
        "FASTAPI_REPL_READ_ONLY": "true",
        "FASTAPI_REPL_MODELS": '["sa_sync_app.models"]',
    }
    kernel_config = load_config(environ=env, load_env_file=False).config
    assert kernel_config.read_only is True
    assert kernel_config.models == ["sa_sync_app.models"]
