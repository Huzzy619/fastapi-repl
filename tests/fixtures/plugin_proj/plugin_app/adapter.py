"""A tiny adapter for a made-up in-memory ORM, as shown in the docs."""

from fastapi_repl import ModelInfo, ORMAdapter

EVENTS: list[str] = []


class Model:
    registry: list[type] = []

    def __init_subclass__(cls) -> None:
        Model.registry.append(cls)


class Person(Model):
    pass


class Pet(Model):
    pass


class Database:
    def __init__(self) -> None:
        self.printer = None

    async def query(self, sql: str) -> list[str]:
        if self.printer:
            self.printer(sql)
        return ["row"]


class InMemoryAdapter(ORMAdapter):
    name = "inmemory"
    display_name = "InMemory ORM"

    async def setup(self) -> None:
        self.db = Database()
        EVENTS.append("setup")

    def discover_models(self):
        for cls in Model.registry:
            yield ModelInfo.from_class(cls, self.name)

    def default_imports(self) -> list[str]:
        return ["from plugin_app.adapter import Model"]

    def objects(self) -> dict:
        return {"db": self.db, "greeting": self.context.options.get("greeting")}

    def enable_sql_echo(self, printer) -> None:
        self.db.printer = printer

    async def teardown(self) -> None:
        EVENTS.append("teardown")

    def tip(self, namespace: dict) -> str:
        return "await db.query('select 1')"
