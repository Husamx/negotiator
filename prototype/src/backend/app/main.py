from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import PROTOTYPE_DIR
from app.storage.db import init_db


app = FastAPI(title="NeGot Prototype", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

ui_dir = PROTOTYPE_DIR / "src" / "frontend" / "app"
if ui_dir.exists():
    # Serve the frontend bundle directly from the prototype folder.
    app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")


@app.on_event("startup")
def _startup() -> None:
    """Initialize the SQLite database on application startup.

    The database is created on-demand if it doesn't already exist.
    """
    init_db()


@app.get("/")
def root():
    """Redirect the root path to the UI entrypoint.

    Keeps the backend landing page aligned with the frontend shell.
    """
    return RedirectResponse("/ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
