# Recipes

## Always have your settings and services at hand

```toml
[tool.fastapi-repl]
imports = [
  "from app.core.config import settings",
  "from app.services import billing, emails",
  "import datetime as dt",
  "from pprint import pp",
]
```

## A "src" layout

```toml
[tool.fastapi-repl]
pythonpath = ["src"]
app = "myapp.main:app"
```

## Run the app's startup code

When your app opens clients or pools in its lifespan (Redis, httpx, Tortoise):

```toml
[tool.fastapi-repl]
app = "app.main:app"
lifespan = true
```

Whatever the lifespan yields is available as `lifespan_state`, and `app.state` works as
it does in a request.

## Names that need async setup

Factories in `objects` can be async; they are awaited on the session loop:

```python title="app/shell.py"
async def admin():
    from app.db import SessionLocal
    from app.models import User
    from sqlalchemy import select

    async with SessionLocal() as s:
        return await s.scalar(select(User).where(User.email == "admin@example.com"))
```

```toml
[tool.fastapi-repl.objects]
admin = "app.shell:admin()"
```

For several names at once, use a namespace hook that returns a dict:

```toml
[tool.fastapi-repl.hooks]
namespace = ["app.shell:extra_names"]
```

## A different database for the shell

Use environment variables so nothing is committed:

```console
DATABASE_URL=postgresql+asyncpg://readonly@replica/app fastapi-repl
```

or keep a second env file:

```console
fastapi-repl --env-file .env.staging
```

## A production warning

```toml
[tool.fastapi-repl]
banner = "[bold red]Connected to the database in DATABASE_URL. Be careful.[/]"
```

The banner accepts [Rich markup](https://rich.readthedocs.io/en/stable/markup.html).

## Personal preferences without touching the team config

Environment variables override the project config, so put personal defaults in your
shell profile:

```console
export FASTAPI_REPL_INTERFACE=ptpython
export FASTAPI_REPL_QUIET=1
```

## One-off scripts and data fixes

```python title="scripts/backfill_slugs.py"
import sys

from slugify import slugify

dry_run = "--dry-run" in sys.argv
posts = (await session.scalars(select(Post).where(Post.slug.is_(None)))).all()
for post in posts:
    post.slug = slugify(post.title)
print(f"{len(posts)} posts")
if not dry_run:
    await session.commit()
```

```console
fastapi-repl run scripts/backfill_slugs.py --dry-run
```

Scripts get the whole namespace, top-level `await` and the arguments after the script
name in `sys.argv`. Modules work too: `fastapi-repl run app.tasks.cleanup --func main`
imports the module and calls (and awaits) `main()`.

## Check that everything imports, in CI

```console
fastapi-repl --strict --no-lifespan -c "pass"
```

This fails when a model module, import or object is broken. Combine with
`fastapi-repl doctor` for a readable report.

## Poke at a running script

```python
from fastapi_repl import embed


def reconcile(invoice_id: int) -> None:
    invoice = load_invoice(invoice_id)
    if invoice.total != invoice.paid:
        embed()  # opens a shell with `invoice`, your models and a session
```

## Use the namespace in your own tools

```python
from fastapi_repl import build_namespace

session, ns = build_namespace(quiet=True)
try:
    count = session.runtime.run(
        ns["session"].scalar(ns["select"](ns["func"].count()).select_from(ns["User"]))
    )
finally:
    session.close()
```

## Makefile and just targets

```make
shell:
	uv run fastapi-repl
```

```just
shell *args:
    uv run fastapi-repl {{args}}
```
