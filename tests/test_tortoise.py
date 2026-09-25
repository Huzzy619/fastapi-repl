from __future__ import annotations

from fastapi_repl.config import load_config
from fastapi_repl.session import ReplSession


def test_tortoise_project(project, invoke) -> None:
    project("tortoise_proj")
    code = (
        "t = await Tournament.create(name='Cup')\n"
        "await Event.create(name='Final', tournament=t)\n"
        "print(await Event.filter(tournament__name='Cup').count())\n"
        "print(await Tournament.filter(Q(name='Cup')).annotate(n=Count('events'))"
        ".values_list('n', flat=True))\n"
    )
    result = invoke("-c", code)
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["1", "[1]"]


def test_tortoise_can_start_twice(project, invoke) -> None:
    project("tortoise_proj")
    for _ in range(2):
        result = invoke("-c", "print(await Tournament.all().count())")
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == "0"


def test_tortoise_models_and_helpers(project) -> None:
    project("tortoise_proj")
    with ReplSession(load_config()) as session:
        ns = session.namespace.to_dict()
        assert {"Tournament", "Event"} <= set(ns)
        assert "TimestampMixin" not in ns
        assert {"Q", "F", "Count", "in_transaction", "Tortoise"} <= set(ns)
        assert [a.name for a in session.adapters] == ["tortoise"]


def test_tortoise_print_sql(project, invoke) -> None:
    project("tortoise_proj")
    result = invoke("--print-sql", "-c", "await Tournament.create(name='X')")
    assert result.exit_code == 0, result.output
    assert 'INSERT INTO "tournament"' in result.stderr
    assert "params:" in result.stderr


def test_tortoise_models_without_init_are_scanned(project, invoke) -> None:
    root = project("tortoise_proj")
    (root / "pyproject.toml").write_text('[tool.fastapi-repl]\nmodels = ["tortoise_app.models"]\n')
    result = invoke("imports", "--json")
    assert '"Tournament"' in result.stdout
    assert '"TimestampMixin"' not in result.stdout
