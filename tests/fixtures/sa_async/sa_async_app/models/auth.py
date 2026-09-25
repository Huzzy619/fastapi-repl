from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sa_async_app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    posts: Mapped[list["Post"]] = relationship(back_populates="author")  # noqa: F821
