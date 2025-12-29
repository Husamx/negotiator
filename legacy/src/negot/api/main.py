"""
FastAPI application entry point.

This module instantiates the FastAPI app, registers API routers and
defines application startup and shutdown hooks. It also configures
CORS for the UI. When run via ``uvicorn`` the app will be served as an
ASGI application.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..core.config import get_settings
from ..core.db import init_db_schema
from .routers import admin as admin_router
from .routers import facts as facts_router
from .routers import knowledge_edges as knowledge_edges_router
from .routers import knowledge_graph as kg_router
from .routers import relationships as relationships_router
from .routers import sessions as sessions_router
from .routers import strategies as strategies_router
from .routers import templates as templates_router
from .routers import users as users_router


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover
    """Application lifespan hook.

    On startup this hook creates the database schema when running
    against SQLite or other non‑migrated databases. In production you
    should rely on Alembic migrations instead. Additional startup
    tasks (e.g., warming caches) can be added here.
    """
    settings = get_settings()
    if settings.env in {"dev", "test"}:
        logger.info("Initialising database schema…")
        await init_db_schema()
    yield


def create_app() -> FastAPI:
    """Factory for the FastAPI app."""
    settings = get_settings()
    app = FastAPI(title="Negotiation Companion API", version="0.1.0", lifespan=lifespan)
    # CORS for local development and the Streamlit UI
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production restrict to specific origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Register routers
    app.include_router(sessions_router.router)
    app.include_router(kg_router.router)
    app.include_router(facts_router.router)
    app.include_router(relationships_router.router)
    app.include_router(knowledge_edges_router.router)
    app.include_router(templates_router.router)
    app.include_router(strategies_router.router)
    app.include_router(admin_router.router)
    app.include_router(users_router.router)
    return app


app = create_app()
