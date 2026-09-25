"""A second model called Tag, to exercise collision handling."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from sa_async_app.db import Base


class Tag(Base):
    __tablename__ = "legacy_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
