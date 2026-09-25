# Tortoise ORM

The Tortoise adapter supports Tortoise ORM 0.21 and newer, including the 1.x series with
its context-based state.

## Setup

Point the adapter at the same config your app uses:

```toml
[tool.fastapi-repl]
models = ["app.models"]

[tool.fastapi-repl.tortoise]
config = "app.db:TORTOISE_ORM"
```

or give it a URL and modules directly:

```toml
[tool.fastapi-repl.tortoise]
db_url = "sqlite://db.sqlite3"
modules = { models = ["app.models"] }
```

fastapi-repl calls `Tortoise.init()` before the shell opens and
`Tortoise.close_connections()` when it exits.

### Using your app's lifespan instead

If your app initialises Tortoise at startup (for example with `RegisterTortoise` in its
lifespan), run the lifespan and skip the `[tortoise]` table entirely:

```toml
[tool.fastapi-repl]
app = "app.main:app"
lifespan = true
```

The adapter sees that Tortoise is already initialised and leaves it alone.

## In the shell

<!-- test: tortoise_proj -->
```python
cup = await Tournament.create(name="World Cup")
await Event.create(name="Final", tournament=cup)

await Event.filter(tournament__name="World Cup").count()
await Tournament.filter(Q(name__icontains="cup")).annotate(n=Count("events")).values("name", "n")

async with in_transaction():
    await Tournament.filter(name="World Cup").update(name="Cup")
```

## What gets loaded

| Name                                | What it is                                   |
| ----------------------------------- | -------------------------------------------- |
| Every model                         | From `Tortoise.apps`, or scanned from `models` if Tortoise is not initialised. |
| `Tortoise`, `connections`           | For raw access and introspection.            |
| `Q`, `F`                            | Query expressions.                           |
| `Count`, `Sum`, `Avg`, `Max`, `Min` | Aggregate functions.                         |
| `in_transaction`                    | Transaction context manager.                 |

When two apps have models with the same name, the later one is loaded with its app
label as a prefix (`events_Tournament`). App labels also work in `dont_load`.

## Printing SQL

`--print-sql` listens to Tortoise's `tortoise.db_client` logger and prints each query
with its parameters.
