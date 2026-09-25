from __future__ import annotations

import asyncio
from typing import Any

import pytest

import fastapi_repl
from fastapi_repl import ReplError, build_namespace, embed
from fastapi_repl.interfaces.python import PythonInterface


def test_public_api_exports() -> None:
    for name in fastapi_repl.__all__:
        assert hasattr(fastapi_repl, name)


def test_build_namespace(project) -> None:
    project("sa_async")
    session, ns = build_namespace(print_sql=False)
    try:
        assert session.runtime is not None
        count = session.runtime.run(
            ns["session"].scalar(ns["select"](ns["func"].count(ns["User"].id)))
        )
        assert count == 2
    finally:
        session.close()


def test_embed_includes_caller_variables(project, monkeypatch) -> None:
    project("sa_async")
    seen: dict[str, Any] = {}

    def fake_start(self: PythonInterface) -> None:
        seen.update(self.context.namespace)

    monkeypatch.setattr(PythonInterface, "start", fake_start)
    local_value = "from the caller"  # noqa: F841
    embed({"extra": 1}, interface="python", banner=False)
    assert seen["local_value"] == "from the caller"
    assert seen["extra"] == 1
    assert "User" in seen
    assert "session" in seen


def test_embed_refuses_running_loop() -> None:
    async def inside() -> None:
        embed()

    with pytest.raises(ReplError, match="running event loop"):
        asyncio.run(inside())


def test_cli_can_be_mounted_in_another_typer_app() -> None:
    import typer
    from typer.testing import CliRunner

    outer = typer.Typer()

    @outer.command()
    def hello() -> None:
        print("hello")

    outer.add_typer(fastapi_repl.cli, name="shell")
    result = CliRunner().invoke(outer, ["shell", "--help"])
    assert result.exit_code == 0
    assert "imports" in result.stdout
