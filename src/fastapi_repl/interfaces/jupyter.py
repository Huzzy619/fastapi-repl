"""Jupyter integration: an IPython kernel with the shell namespace, and notebook launchers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi_repl.errors import InterfaceUnavailableError
from fastapi_repl.interfaces.base import Interface

KERNEL_NAME = "fastapi-repl"


class KernelInterface(Interface):
    """Runs an IPython kernel whose namespace is the shell namespace.

    This is what notebooks started with ``--notebook`` / ``--lab`` connect to,
    and it can be used directly with ``--kernel`` (for example from VS Code or
    ``jupyter console --existing``).
    """

    name = "kernel"
    display_name = "IPython kernel"
    package = "ipykernel"
    distribution = "ipykernel"

    def __init__(self, context: Any, connection_file: str | None = None) -> None:
        super().__init__(context)
        self.connection_file = connection_file

    @classmethod
    def install_hint(cls) -> str:
        return "pip install 'fastapi-repl[jupyter]'"

    def start(self) -> None:
        from ipykernel.kernelapp import IPKernelApp

        argv: list[str] = []
        if self.connection_file:
            argv += ["-f", self.connection_file]
        app = IPKernelApp.instance(user_ns=self.context.namespace)
        app.initialize(argv)
        try:
            app.start()
        finally:
            IPKernelApp.clear_instance()


def write_kernelspec(directory: Path, argv: list[str], display_name: str) -> Path:
    """Write a kernelspec under ``directory/kernels/fastapi-repl``."""
    spec_dir = directory / "kernels" / KERNEL_NAME
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "argv": argv,
        "display_name": display_name,
        "language": "python",
        "metadata": {"debugger": True},
    }
    (spec_dir / "kernel.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec_dir


def kernel_argv(config_file: Path | None) -> list[str]:
    argv = [sys.executable, "-m", "fastapi_repl", "shell", "--kernel"]
    if config_file is not None:
        argv += ["--config", str(config_file)]
    argv += ["--connection-file", "{connection_file}"]
    return argv


def launch_jupyter(
    app: str,
    *,
    root: Path,
    config_file: Path | None,
    extra_args: list[str],
    env_overrides: dict[str, str] | None = None,
) -> int:
    """Start ``jupyter lab`` or ``jupyter notebook`` with a fastapi-repl kernel as default.

    The kernelspec lives in a temporary directory added to ``JUPYTER_PATH``,
    so nothing is installed permanently. ``env_overrides`` reach the kernels,
    which is how command-line flags such as ``--read-only`` apply to them.
    """
    jupyter = shutil.which("jupyter")
    if jupyter is None:
        candidate = Path(sys.executable).parent / "jupyter"
        jupyter = str(candidate) if candidate.exists() else None
    if jupyter is None:
        raise InterfaceUnavailableError(
            "Jupyter is not installed. Install it with: pip install 'fastapi-repl[jupyter]'"
        )
    with tempfile.TemporaryDirectory(prefix="fastapi-repl-") as tmp:
        write_kernelspec(
            Path(tmp),
            kernel_argv(config_file),
            display_name=f"fastapi-repl ({root.name})",
        )
        env = {**os.environ, **(env_overrides or {})}
        env["JUPYTER_PATH"] = os.pathsep.join(filter(None, [tmp, env.get("JUPYTER_PATH")]))
        cmd = [
            jupyter,
            app,
            f"--MultiKernelManager.default_kernel_name={KERNEL_NAME}",
            *extra_args,
        ]
        return subprocess.call(cmd, cwd=root, env=env)
