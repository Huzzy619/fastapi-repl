from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fastapi_repl import __version__


def test_version(invoke) -> None:
    result = invoke("--version")
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_commands(invoke) -> None:
    result = invoke("--help")
    assert result.exit_code == 0
    for command in ("shell", "run", "imports", "config", "init", "doctor"):
        assert command in result.stdout


def test_shell_options_work_without_subcommand(project, invoke) -> None:
    project("sa_async")
    result = invoke("--quiet", "-c", "print(1 + 1)")
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "2"


def test_explicit_shell_subcommand(project, invoke) -> None:
    project("sa_async")
    result = invoke("shell", "-c", "print(type(session).__name__)")
    assert result.stdout.strip() == "AsyncSession"


def test_command_error_exit_code_and_clean_traceback(project, invoke) -> None:
    project("sa_async")
    result = invoke("-c", "def f():\n    raise ValueError('boom')\nf()")
    assert result.exit_code == 1
    assert "ValueError: boom" in result.stderr
    assert "fastapi_repl" not in result.stderr


def test_system_exit_code_is_forwarded(project, invoke) -> None:
    project("sa_async")
    assert invoke("-c", "raise SystemExit(3)").exit_code == 3


def test_extra_import_flag(project, invoke) -> None:
    project("sa_async")
    result = invoke("-I", "import textwrap", "-c", "print(textwrap.dedent('  x'))")
    assert result.stdout.strip() == "x"


def test_no_imports_gives_bare_namespace(project, invoke) -> None:
    project("sa_async")
    result = invoke(
        "--no-imports", "-c", "print(sorted(k for k in dir() if not k.startswith('_')))"
    )
    assert result.stdout.strip() == "['await_']"


def test_no_models_and_no_helpers(project, invoke) -> None:
    project("sa_async")
    result = invoke(
        "--no-models",
        "--no-helpers",
        "-c",
        "print('User' in dir(), 'select' in dir(), 'session' in dir())",
    )
    assert result.stdout.strip() == "False False True"


def test_conflicting_interfaces(project, invoke) -> None:
    project("sa_async")
    result = invoke("--ipython", "--bpython")
    assert result.exit_code == 1
    assert "single interface" in result.stderr


def test_conflicting_modes(project, invoke) -> None:
    project("sa_async")
    result = invoke("--kernel", "-c", "1")
    assert result.exit_code == 1
    assert "cannot be combined" in result.stderr


def test_import_failures_are_reported_not_fatal(project, invoke) -> None:
    root = project("sa_async")
    with (root / "pyproject.toml").open("a") as fh:
        fh.write('\n[tool.fastapi-repl.objects]\nbroken = "sa_async_app.nope:thing"\n')
    result = invoke("-c", "print('still works')")
    assert result.exit_code == 0
    assert "still works" in result.stdout
    assert "sa_async_app.nope" in result.stderr


def test_strict_makes_failures_fatal(project, invoke) -> None:
    root = project("sa_async")
    with (root / "pyproject.toml").open("a") as fh:
        fh.write('\n[tool.fastapi-repl.objects]\nbroken = "sa_async_app.nope:thing"\n')
    result = invoke("--strict", "-c", "print('nope')")
    assert result.exit_code == 1
    assert "nope" not in result.stdout


def test_config_errors_are_friendly(tmp_path: Path, monkeypatch, invoke) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "fastapi-repl.toml").write_text("interfce = 'ipython'\n")
    result = invoke("-c", "1")
    assert result.exit_code == 1
    assert "Unknown setting 'interfce'" in result.stderr
    assert "Traceback" not in result.stderr


def test_imports_json(project, invoke) -> None:
    project("sa_async")
    payload = json.loads(invoke("imports", "--json").stdout)
    by_name = {n["name"]: n for n in payload["names"]}
    assert by_name["User"]["group"] == "models"
    assert by_name["User"]["source"] == "sa_async_app.models.auth.User"
    assert by_name["session"]["type"] == "AsyncSession"
    assert payload["adapters"] == ["sqlalchemy"]
    assert payload["notes"]


def test_imports_table(project, invoke) -> None:
    project("sa_async")
    result = invoke("imports")
    assert "Shell namespace" in result.stdout
    assert "legacy_Tag" in result.stdout


def test_config_command(project, invoke, monkeypatch) -> None:
    project("sa_async")
    monkeypatch.setenv("FASTAPI_REPL_PRINT_SQL", "true")
    payload = json.loads(invoke("config", "--json").stdout)
    assert payload["settings"]["print_sql"] == {
        "value": True,
        "source": "env FASTAPI_REPL_PRINT_SQL",
    }
    assert payload["settings"]["sqlalchemy.engine"]["value"] == "sa_async_app.db:engine"
    table = invoke("config", "--changed").stdout
    assert "print_sql" in table
    assert "interface_order" not in table


def test_run_script(project, invoke, tmp_path: Path) -> None:
    project("sa_async")
    script = tmp_path / "script.py"
    script.write_text(
        "import sys\n"
        "print('argv', sys.argv[1:])\n"
        "print('users', await session.scalar(select(func.count(User.id))))\n"
        "async def main():\n"
        "    print('main', __name__)\n"
    )
    result = invoke("run", str(script), "--func", "main", "--", "--flag", "x")
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["argv ['--flag', 'x']", "users 2", "main __main__"]


def test_run_module(project, invoke) -> None:
    root = project("sa_async")
    (root / "sa_async_app" / "task.py").write_text("print('task', settings.app_name)\n")
    result = invoke("run", "sa_async_app.task")
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "task sa-async-fixture"


def test_run_missing_script(project, invoke) -> None:
    project("sa_async")
    result = invoke("run", "missing.py")
    assert result.exit_code == 1
    assert "does not exist" in result.stderr


def test_run_missing_function(project, invoke, tmp_path: Path) -> None:
    project("sa_async")
    script = tmp_path / "s.py"
    script.write_text("x = 1\n")
    result = invoke("run", str(script), "-f", "main")
    assert result.exit_code == 1
    assert "no function named 'main'" in result.stderr


def test_doctor_ok(project, invoke) -> None:
    project("sa_async")
    result = invoke("doctor")
    assert result.exit_code == 0, result.output
    assert "Everything looks good" in result.stdout
    assert "SQLAlchemy" in result.stdout


def test_doctor_reports_problems(project, invoke) -> None:
    root = project("sa_async")
    with (root / "pyproject.toml").open("a") as fh:
        fh.write('\n[tool.fastapi-repl.objects]\nbroken = "sa_async_app.nope:thing"\n')
    result = invoke("doctor")
    assert result.exit_code == 1
    assert "problem(s) found" in result.stdout


@pytest.mark.parametrize("flag", ["--notebook", "--lab"])
def test_jupyter_launcher(project, invoke, monkeypatch, flag: str) -> None:
    project("sa_async")
    calls = []

    def fake_call(cmd, cwd, env):
        # os.pathsep: ":" on Unix, ";" on Windows (":" would split "C:\\Users\\...").
        spec_dir = Path(env["JUPYTER_PATH"].split(os.pathsep)[0]) / "kernels" / "fastapi-repl"
        calls.append((cmd, json.loads((spec_dir / "kernel.json").read_text())))
        return 0

    monkeypatch.setattr("fastapi_repl.interfaces.jupyter.shutil.which", lambda _: "/bin/jupyter")
    monkeypatch.setattr("fastapi_repl.interfaces.jupyter.subprocess.call", fake_call)
    result = invoke(flag, "--jupyter-arguments", "--no-browser --port 9999")
    assert result.exit_code == 0, result.output
    [(cmd, spec)] = calls
    assert cmd[1] == flag.lstrip("-")
    assert "--MultiKernelManager.default_kernel_name=fastapi-repl" in cmd
    assert cmd[-3:] == ["--no-browser", "--port", "9999"]
    assert spec["argv"][1:5] == ["-m", "fastapi_repl", "shell", "--kernel"]
    assert "{connection_file}" in spec["argv"]
