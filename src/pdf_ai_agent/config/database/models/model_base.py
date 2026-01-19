
from datetime import datetime


from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.ext.declarative import as_declarative, declared_attr
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import (
    DateTime,
    func,
)

class Base(AsyncAttrs, DeclarativeBase):
    __abstract__ = True

    pass

class TimestampMixin:
    
    created_at: Mapped[datetime] = mapped_column("created_at", DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column("updated_at", DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class CreatedMixin:

    created_at: Mapped[datetime] = mapped_column("created_at", DateTime, server_default=func.now(), nullable=False)