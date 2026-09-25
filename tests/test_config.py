from __future__ import annotations

from pathlib import Path

import pytest

from fastapi_repl.config import ReplConfig, find_project_root, load_config
from fastapi_repl.errors import ConfigError


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_defaults_without_any_config(tmp_path: Path) -> None:
    loaded = load_config(cwd=tmp_path, environ={})
    assert loaded.config == ReplConfig()
    assert loaded.root == tmp_path.resolve()
    assert loaded.files == []
    assert loaded.source_of("interface") == "default"


def test_precedence_pyproject_then_standalone_then_env_then_cli(tmp_path: Path) -> None:
    write(
        tmp_path / "pyproject.toml",
        '[tool.fastapi-repl]\ninterface = "ptpython"\nquiet = true\nverbose = true\n'
        'models = ["a"]\n',
    )
    write(tmp_path / "fastapi-repl.toml", 'quiet = false\nmodels = ["b"]\n')
    env = {"FASTAPI_REPL_MODELS": "c, d", "FASTAPI_REPL_VERBOSE": "false"}
    loaded = load_config(cwd=tmp_path, environ=env, cli={"interface": "python"})
    config = loaded.config
    assert config.interface == "python"
    assert config.quiet is False
    assert config.models == ["c", "d"]
    assert config.verbose is False
    assert loaded.source_of("interface") == "command line"
    assert loaded.source_of("quiet") == "fastapi-repl.toml"
    assert loaded.source_of("models") == "env FASTAPI_REPL_MODELS"
    assert [f.name for f in loaded.files] == ["pyproject.toml", "fastapi-repl.toml"]


def test_dashed_keys_and_nested_tables(tmp_path: Path) -> None:
    write(
        tmp_path / "fastapi-repl.toml",
        'print-sql = true\ndont-load = "Audit*"\n[sqlalchemy]\nsession-name = "db"\n'
        '[objects]\nmy-thing = "x:y"\n',
    )
    config = load_config(cwd=tmp_path, environ={}).config
    assert config.print_sql is True
    assert config.dont_load == ["Audit*"]
    assert config.sqlalchemy.session_name == "db"
    assert config.objects == {"my-thing": "x:y"}


def test_unknown_key_is_an_error(tmp_path: Path) -> None:
    write(tmp_path / "fastapi-repl.toml", "prnt_sql = true\n")
    with pytest.raises(ConfigError, match="Unknown setting 'prnt_sql'"):
        load_config(cwd=tmp_path, environ={})


def test_unknown_section_key_is_an_error(tmp_path: Path) -> None:
    write(tmp_path / "fastapi-repl.toml", "[sqlalchemy]\nengin = 'x:y'\n")
    with pytest.raises(ConfigError, match=r"sqlalchemy\.engin"):
        load_config(cwd=tmp_path, environ={})


def test_invalid_value_mentions_source(tmp_path: Path) -> None:
    write(tmp_path / "fastapi-repl.toml", 'interface = "emacs"\n')
    with pytest.raises(ConfigError, match=r"interface.*fastapi-repl\.toml"):
        load_config(cwd=tmp_path, environ={})


def test_invalid_toml(tmp_path: Path) -> None:
    write(tmp_path / "fastapi-repl.toml", "this is = = not toml")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(cwd=tmp_path, environ={})


def test_nested_env_vars_and_json(tmp_path: Path) -> None:
    env = {
        "FASTAPI_REPL_SQLALCHEMY__ENGINE": "app.db:engine",
        "FASTAPI_REPL_OBJECTS": '{"redis": "app.cache:redis"}',
        "FASTAPI_REPL_TRUNCATE_SQL": "200",
        "FASTAPI_REPL_NOPE": "1",
    }
    loaded = load_config(cwd=tmp_path, environ=env)
    assert loaded.config.sqlalchemy.engine == "app.db:engine"
    assert loaded.config.objects == {"redis": "app.cache:redis"}
    assert loaded.config.truncate_sql == 200
    assert any("FASTAPI_REPL_NOPE" in w for w in loaded.warnings)
    assert loaded.source_of("sqlalchemy.engine") == "env FASTAPI_REPL_SQLALCHEMY__ENGINE"


def test_fastapi_cli_entrypoint_is_default_app(tmp_path: Path) -> None:
    write(tmp_path / "pyproject.toml", '[tool.fastapi]\nentrypoint = "main:app"\n')
    loaded = load_config(cwd=tmp_path, environ={})
    assert loaded.config.app == "main:app"
    assert "entrypoint" in loaded.source_of("app")


def test_explicit_app_beats_fastapi_entrypoint(tmp_path: Path) -> None:
    write(
        tmp_path / "pyproject.toml",
        '[tool.fastapi]\nentrypoint = "main:app"\n[tool.fastapi-repl]\napp = "other:app"\n',
    )
    assert load_config(cwd=tmp_path, environ={}).config.app == "other:app"


def test_project_root_is_found_from_subdirectory(tmp_path: Path) -> None:
    write(tmp_path / "pyproject.toml", "[tool.fastapi-repl]\n")
    sub = tmp_path / "pkg" / "deep"
    sub.mkdir(parents=True)
    assert find_project_root(sub) == tmp_path.resolve()


def test_root_prefers_config_table_over_nearest_pyproject(tmp_path: Path) -> None:
    write(tmp_path / "pyproject.toml", "[tool.fastapi-repl]\nquiet = true\n")
    write(tmp_path / "sub" / "pyproject.toml", "[project]\nname = 'x'\n")
    assert find_project_root(tmp_path / "sub") == tmp_path.resolve()


def test_explicit_config_file(tmp_path: Path) -> None:
    path = write(tmp_path / "configs" / "shell.toml", "quiet = true\n")
    loaded = load_config(config_file=path, environ={})
    assert loaded.config.quiet is True
    assert loaded.root == path.parent.resolve()


def test_explicit_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="does not exist"):
        load_config(config_file=tmp_path / "missing.toml", environ={})


def test_env_file_is_loaded_and_can_set_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FIXTURE_SECRET", raising=False)
    write(tmp_path / "fastapi-repl.toml", 'env_file = ".env"\n')
    write(tmp_path / ".env", "FIXTURE_SECRET=s3cret\nFASTAPI_REPL_QUIET=1\n")
    import os

    try:
        loaded = load_config(cwd=tmp_path)
        assert os.environ["FIXTURE_SECRET"] == "s3cret"
        assert loaded.config.quiet is True
    finally:
        os.environ.pop("FIXTURE_SECRET", None)
        os.environ.pop("FASTAPI_REPL_QUIET", None)


def test_missing_env_file_warns(tmp_path: Path) -> None:
    write(tmp_path / "fastapi-repl.toml", 'env_file = ".env.missing"\n')
    loaded = load_config(cwd=tmp_path, environ={})
    assert any("does not exist" in w for w in loaded.warnings)


def test_scalar_strings_become_lists(tmp_path: Path) -> None:
    write(tmp_path / "fastapi-repl.toml", 'models = "app.models"\nbase = "app.db:Base"\n')
    config = load_config(cwd=tmp_path, environ={}).config
    assert config.models == ["app.models"]
    assert config.base == ["app.db:Base"]
