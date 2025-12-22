"""
Database setup for the Negotiation Companion.

This module provides an asynchronous SQLAlchemy engine, a scoped session
factory and helper functions for running migrations or creating the
database schema programmatically in development and testing.

The application relies on PostgreSQL in production but defaults to
SQLite for testing if the environment variable `DATABASE_URL` is
pointed at a SQLite URI. Asynchronous ORM usage is built on top of
``asyncpg`` for PostgreSQL and ``aiosqlite`` for SQLite.
"""
from __future__ import annotations

import contextlib
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):  # type: ignore[call-arg]
    """Base class for declarative SQLAlchemy models.

    All ORM models should inherit from this class. It configures
    automatic table naming conventions and uses the metadata from
    SQLAlchemy to generate schema definitions. See ``negot/core/models.py``
    for the actual model definitions.
    """

    pass


from functools import lru_cache


def _create_engine(db_url: str, echo: bool) -> "sqlalchemy.ext.asyncio.AsyncEngine":
    """Instantiate a new async engine from the given URL."""
    return create_async_engine(db_url, echo=echo)


@lru_cache(maxsize=1)
def get_engine() -> "sqlalchemy.ext.asyncio.AsyncEngine":
    """Return a cached asynchronous SQLAlchemy engine.

    This function reads the database URL from the current settings
    (``get_settings()``) and creates an engine accordingly. Using a
    cached engine allows tests to override the ``DATABASE_URL``
    environment variable and ensure a fresh engine is created.
    """
    settings = get_settings()
    return _create_engine(settings.database_url, echo=settings.env == "dev")


@lru_cache(maxsize=1)
def get_async_session_factory() -> async_sessionmaker:
    """Return a cached session factory bound to the current engine."""
    return async_sessionmaker(
        bind=get_engine(), expire_on_commit=False, class_=AsyncSession
    )


@contextlib.asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Asynchronous context manager that yields a database session.

    This helper is intended to be used as a dependency in FastAPI
    endpoints and services. It ensures that sessions are properly
    committed or rolled back and closed when the request finishes.

    Example:

    >>> async with get_db_session() as session:
    ...     result = await session.execute(select(Model).where(...))
    ...     # do something with result
    """
    async with get_async_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db_schema() -> None:
    """Create all tables in the database.

    This helper is useful for development and testing where migrations
    may not have run. It imports the models module to ensure all
    metadata is registered on the declarative base and then creates
    all tables. In production environments Alembic migrations should
    be used instead of this function.
    """
    # Import models so that they are registered on the metadata
    from . import models  # noqa: F401

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)