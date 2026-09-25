"""Drive an interactive fastapi-repl session through a pseudo-terminal (POSIX only)."""

from __future__ import annotations

import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][0-9A-Za-z]|\x1b[=>]|\r")


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def run_interactive(
    args: list[str],
    lines: list[str],
    *,
    cwd: Path,
    timeout: float = 60.0,
    wait_for: str = "fastapi-repl",
    env: dict[str, str] | None = None,
) -> str:
    """Start ``fastapi-repl`` in a pty, type ``lines`` and return everything printed."""
    import pty

    master, slave = pty.openpty()
    full_env = {**os.environ, "TERM": "dumb", "COLUMNS": "120", "LINES": "40", **(env or {})}
    proc = subprocess.Popen(
        [sys.executable, "-m", "fastapi_repl", *args],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=cwd,
        env=full_env,
        close_fds=True,
    )
    os.close(slave)
    output = b""

    def read_for(seconds: float, until: str | None = None) -> None:
        nonlocal output
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    return
                if not chunk:
                    return
                output += chunk
                if until and until in strip_ansi(output.decode(errors="replace")):
                    return
            elif proc.poll() is not None:
                return

    try:
        read_for(timeout, until=wait_for)
        for line in lines:
            time.sleep(0.4)
            os.write(master, line.encode() + b"\r")
            read_for(2.0)
        read_for(5.0)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        os.close(master)
    return strip_ansi(output.decode(errors="replace"))
