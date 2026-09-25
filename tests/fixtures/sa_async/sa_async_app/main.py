from contextlib import asynccontextmanager

from fastapi import FastAPI

EVENTS: list[str] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    EVENTS.append("startup")
    yield {"greeting": "hello from lifespan"}
    EVENTS.append("shutdown")


app = FastAPI(lifespan=lifespan)


@app.get("/")
def index() -> dict[str, str]:
    return {"ok": "yes"}
