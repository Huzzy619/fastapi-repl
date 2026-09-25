# Security

fastapi-repl is a developer tool that runs your code with your credentials. This page
explains what that means and how to use it safely, especially near production data.

## The config is code

Everything that names a Python object runs code when the shell starts: `app`, `models`,
`base`, `imports`, `objects`, hooks and adapters. So do `FASTAPI_REPL_*` environment
variables, including ones in your `env_file`.

That is the same trust level as your project itself: anyone who can edit your
`pyproject.toml` or `.env` can already change your code. But it means:

- Do not run `fastapi-repl` inside a project you do not trust, just as you would not
  run its tests or `python manage.py`.
- Treat `FASTAPI_REPL_*` variables on shared machines and CI runners as code.

## Know which database you are on

The banner shows the database the shell is connected to (without the password):

```text
Database     postgresql+asyncpg://app:***@db.internal:5432/app
```

Check it before you type anything that writes. `fastapi-repl doctor` shows the same
line. To make a production connection impossible to miss, add a banner message through
an environment variable that only exists on that machine:

```console
export FASTAPI_REPL_BANNER="[bold red]PRODUCTION DATABASE[/]"
```

## Read-only sessions

For looking at data you must not change, start the shell read-only:

```console
fastapi-repl --read-only
```

On PostgreSQL and SQLite every connection is switched to read-only, and writes fail with
a database error. If fastapi-repl cannot enforce it for your database or ORM, it refuses
to start instead of quietly giving you write access. See
[`read_only`](configuration.md#read_only).

`read_only` guards against mistakes. For access that must be read-only whatever
happens, connect with a database role that only has `SELECT` rights, for example with a
separate env file:

```console
fastapi-repl --env-file .env.readonly --read-only
```

## Open transactions hold locks

An SQLAlchemy session starts a transaction with your first query and keeps it open until
you `commit()`, `rollback()` or exit. While it is open on PostgreSQL:

- Tables you read are locked against schema changes, so an `alembic upgrade` that alters
  them waits for your shell. Worse, while the migration waits, the app's own queries on
  those tables queue behind it.
- Servers with `idle_in_transaction_session_timeout` will close your connection, and your
  next statement fails.

So on a shared database, end transactions you no longer need, and do not leave a shell
open for hours:

```python
await session.rollback()  # or commit()
```

## Secrets on screen and on disk

- **`--print-sql` prints bound parameters**, which can include password hashes, tokens
  and personal data. Avoid it when sharing your screen or recording a terminal.
- **History files** (`~/.cache/fastapi-repl/`) keep what you typed. fastapi-repl creates
  them readable only by you, but do not paste secrets at the prompt.
- **Tracebacks** can include values from your code. Check before pasting them into an
  issue.

## Jupyter

`--notebook` and `--lab` start a Jupyter server whose kernels have your database
connection. Jupyter's defaults are safe: it listens on `localhost` and requires a token.
Do not pass `--ip=0.0.0.0`, disable the token, or expose the port unless you understand
that anyone who can reach it gets a shell with your credentials. Command-line flags such
as `--read-only` apply to the kernels too.

## Production images

Keep fastapi-repl in a development dependency group, not in your runtime dependencies.
If you do need a shell on a server, it is no more dangerous than having IPython there:
it does nothing until someone runs it, and whoever runs it already has shell access.

## Reporting a vulnerability

Please report security problems privately through
[GitHub security advisories](https://github.com/huzzyk/fastapi-repl/security/advisories/new)
rather than a public issue.
