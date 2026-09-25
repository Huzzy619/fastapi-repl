from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest

from fastapi_repl.adapters import available_adapters, load_adapter_class
from fastapi_repl.config import load_config
from fastapi_repl.errors import ConfigError
from fastapi_repl.session import ReplSession


def test_custom_adapter_by_import_path(project, invoke) -> None:
    project("plugin_proj")
    result = invoke("-c", "print(await db.query('select 42'), greeting, Person, Model)")
    assert result.exit_code == 0, result.output
    assert "['row'] hello from plugin options" in result.stdout
    assert "select 42" in result.stderr
    from plugin_app.adapter import EVENTS

    assert EVENTS == ["setup", "teardown"]


def test_custom_adapter_in_banner(project) -> None:
    project("plugin_proj")
    with ReplSession(load_config()) as session:
        assert [a.describe() for a in session.adapters] == ["InMemory ORM"]
        assert list(session.tips()) == ["await db.query('select 1')"]
        models = [e.name for e in session.namespace.by_group()["models"]]
        assert models == ["Person", "Pet"]


def test_entry_point_plugins_are_discovered(monkeypatch) -> None:
    fake = [
        EntryPoint(
            name="inmemory",
            value="plugin_app.adapter:InMemoryAdapter",
            group="fastapi_repl.adapters",
        )
    ]
    monkeypatch.setattr("fastapi_repl.adapters.entry_points", lambda group: fake if group else [])
    adapters = available_adapters()
    assert adapters["inmemory"] == "plugin_app.adapter:InMemoryAdapter"
    assert "sqlalchemy" in adapters


def test_unknown_adapter_name() -> None:
    with pytest.raises(ConfigError, match="Unknown adapter 'nope'"):
        load_adapter_class("nope")


def test_non_adapter_class_rejected() -> None:
    with pytest.raises(ConfigError, match="not an ORMAdapter"):
        load_adapter_class("collections:OrderedDict")
