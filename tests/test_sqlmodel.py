from __future__ import annotations

from fastapi_repl.config import load_config
from fastapi_repl.session import ReplSession


def test_sqlmodel_project(project, invoke) -> None:
    project("sqlmodel_proj")
    with ReplSession(load_config()) as session:
        ns = session.namespace.to_dict()
        assert [a.name for a in session.adapters] == ["sqlmodel"]
        assert "Hero" in ns
        assert "HeroRead" not in ns
        assert type(ns["session"]).__module__.startswith("sqlmodel")
        assert ns["select"].__module__.startswith("sqlmodel")
        assert "app" in ns

    result = invoke("-c", "print(session.exec(select(Hero).where(Hero.power > 5)).one().name)")
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "Rusty-Man"


def test_sqlmodel_app_comes_from_fastapi_entrypoint(project, invoke) -> None:
    project("sqlmodel_proj")
    result = invoke("config", "--json")
    assert '"sqlmodel_app.main:app"' in result.stdout
    assert "[tool.fastapi] entrypoint" in result.stdout
