from fastapi import FastAPI
from sqlmodel import Field, Session, SQLModel, create_engine


class Hero(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    power: int = 0


class HeroRead(SQLModel):
    """Not a table: must not be loaded as a model."""

    name: str


engine = create_engine("sqlite:///./sqlmodel.db")
app = FastAPI()


def create_db() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Hero(name="Deadpond", power=3))
        session.add(Hero(name="Rusty-Man", power=9))
        session.commit()
