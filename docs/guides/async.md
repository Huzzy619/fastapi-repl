# Async and `await`

## The short version

Write `await` at the prompt, like in an `async def`:

```python
user = await session.get(User, 1)
await user.awaitable_attrs.posts
```

It works in IPython, ptpython, ptipython and the plain Python shell, in `-c` code, in
code piped on stdin, and in scripts run with `fastapi-repl run`.

## One loop for the whole session

Async database drivers tie connections to the event loop that created them. Most
homemade shells call `asyncio.run()` for every statement, which creates a fresh loop
each time, and you get errors such as *"Future attached to a different loop"* or
*"another operation is in progress"* on the second query.

fastapi-repl creates **one event loop per session** and runs everything on it: your
app's lifespan, adapter setup, factories in `objects`, hooks, every line you type, and
the cleanup on exit. The connection pool and the session stay valid for as long as the
shell is open.

Context variables set by your code (for example Tortoise 1.x's connection context, or
your own request-scoped context) carry over from one prompt to the next.

## Interrupting

Press ++ctrl+c++ while an `await` is running to cancel it. You get
`KeyboardInterrupt` and a new prompt; the loop and the session stay usable (though you
may need `await session.rollback()` if a transaction was open).

## Background tasks

Tasks you create keep running between prompts only while something is running on the
loop. To let them make progress, await something:

```python
task = asyncio.create_task(worker())
await asyncio.sleep(1)  # the task runs during this second
await task
```

## `await_()`: for shells and code without top-level await

bpython cannot compile top-level `await`, and some code (a debugger, a plain sync
function you define at the prompt) cannot use it either. Use the `await_` helper, which
runs a coroutine on the session loop and returns the result:

```python
def count_users():
    return await_(session.scalar(select(func.count()).select_from(User)))


count_users()
```

`await_` is in every namespace, including scripts.

## Jupyter

The Jupyter kernel uses ipykernel's own event loop, and top-level `await` works as
usual. The session and connections belong to that loop.

## Limits

- `embed()` cannot be called from inside a running event loop (for example from an
  `async def` endpoint), because the shell needs to own the loop. Call it from sync
  code, or use a debugger.
- `--print-sql-location` cannot see your code for async drivers, which run queries in
  a separate greenlet.
