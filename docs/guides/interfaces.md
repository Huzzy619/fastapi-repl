# Interfaces

fastapi-repl can start several interactive shells. Pick one per run with a flag, or set
a default in the config.

| Interface   | Flag            | Install extra     | Top-level `await` | Notes                                  |
| ----------- | --------------- | ----------------- | ----------------- | -------------------------------------- |
| IPython     | `--ipython`     | `[ipython]`       | Yes               | The default when installed.            |
| ptpython    | `--ptpython`    | `[ptpython]`      | Yes               | Autocompletion as you type.            |
| ptipython   | `--ptipython`   | `[ptpython,ipython]` | Yes            | ptpython's UI with IPython magics.     |
| bpython     | `--bpython`     | `[bpython]`       | No, use `await_()`| Inline docs and rewind.                |
| Python      | `--plain`       | none              | Yes               | Always available.                      |
| Jupyter     | `--notebook`, `--lab`, `--kernel` | `[jupyter]` | Yes     | Browser notebooks.                     |

```toml
[tool.fastapi-repl]
interface = "ptpython"                      # or "auto"
interface_order = ["ptpython", "ipython"]   # preference for "auto"
```

`-i/--interface NAME` also works, and so does `FASTAPI_REPL_INTERFACE=ptpython` for a
personal default that you do not want to commit.

## IPython

The shell starts with `autoawait` on and runs your code on the session loop. Your
IPython profile, config, extensions and startup files load as normal. Pass extra
arguments with `--ipython-arguments`:

```console
fastapi-repl --ipython-arguments "--profile=work --no-confirm-exit"
```

## ptpython and ptipython

History is kept in `~/.cache/fastapi-repl/`. Your ptpython config
(`~/.config/ptpython/config.py`) is loaded if present. `exit()` and ++ctrl+d++ quit.

## bpython

bpython cannot compile top-level `await`. Everything else works; wrap coroutines in
`await_()`:

```python
users = await_(session.scalars(select(User))).all()
```

## Plain Python

A `code.InteractiveConsole` with top-level `await`, readline tab completion and history
in `~/.cache/fastapi-repl/python_history`. Like Django's `shell`, it runs `$PYTHONSTARTUP` and
`~/.pythonrc.py` first (turn off with `--no-startup`).

## Jupyter

```console
fastapi-repl --lab                  # JupyterLab
fastapi-repl --notebook             # classic Notebook
fastapi-repl --lab --jupyter-arguments "--no-browser --port=8899"
```

fastapi-repl registers a temporary kernel called **fastapi-repl** that only exists
while the command runs. Each notebook you open with it starts with your namespace
loaded. `--kernel` starts a bare kernel for use with other frontends.

## Non-interactive use

These work with every interface setting:

```console
fastapi-repl -c "print(await session.scalar(select(func.count()).select_from(User)))"
echo "print(User.__table__.c.keys())" | fastapi-repl
fastapi-repl run scripts/backfill.py --dry-run
fastapi-repl run app.tasks.cleanup --func main
```

Errors in `-c`, stdin and scripts print a traceback that starts at your code and exit
with status 1, so they are safe to use in CI and cron jobs.
