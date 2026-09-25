# FAQ

## Does it only work with FastAPI?

No. The name says FastAPI because that is where the gap is most obvious, but nothing
depends on FastAPI. Any Python project with models works, and `app` / `lifespan` work
with any ASGI 3 app: Starlette, Litestar, Quart, Django's ASGI handler and others.

## Is it safe to have in production images?

It is a development tool, like IPython. Keep it in a dev dependency group. If you do
need a shell on a server, installing it there is no different from installing IPython:
it does nothing until you run it.

## Does it change my database?

Only when you do. fastapi-repl opens a session and never commits. The one exception is
opt-in: Tortoise's `generate_schemas = true` creates missing tables.

## Does starting the shell run my app?

Importing `app` runs your module-level code, just like `uvicorn` would. The lifespan
(startup and shutdown) only runs with `lifespan = true` or `--lifespan`. No server is
started and no port is opened.

## Why is my session not an `async with` block?

The shell creates the session for you and closes it when you exit, so you can use it
across prompts. If you prefer your own, turn it off (`session = false`) and use your
session factory as normal.

## Can I use a different ORM?

Yes: [write an adapter](guides/writing-adapters.md). It is usually 30 to 60 lines.
Without an adapter, `imports`, `objects` and hooks already let you load anything.

## How is this different from `python -i` or `IPython.embed()`?

Those give you a prompt. fastapi-repl gives you a prompt with your project loaded and a
working async setup, and cleans up after itself. It is the difference between
`python -i manage.py` and `manage.py shell_plus`.

## Which Python versions are supported?

Python 3.11 and newer.
