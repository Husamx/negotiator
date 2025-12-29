from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    backend_root = Path(__file__).resolve().parent / "src" / "backend"
    sys.path.insert(0, str(backend_root))
    from app.main import app  # noqa: F401

    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
