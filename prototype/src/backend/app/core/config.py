from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


NEGOTIATOR_DIR = Path(__file__).resolve().parents[5]
PROTOTYPE_DIR = NEGOTIATOR_DIR / "prototype"
load_dotenv(PROTOTYPE_DIR / ".env")
DATA_DIR = PROTOTYPE_DIR / "data"
PROMPTS_DIR = DATA_DIR / "prompts"
PERSONAS_DIR = DATA_DIR / "personas"
STRATEGY_DIR = PROTOTYPE_DIR / "strategy_packs" / "core" / "strategies"
DB_PATH = PROTOTYPE_DIR / "negot.db"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
MAX_PARALLEL_RUNS = int(os.getenv("MAX_PARALLEL_RUNS", "4"))

# Allow override via environment variables if needed.

def resolve_path(path: Path) -> Path:
    """Return a resolved filesystem path (placeholder for future overrides).
    """
    return path
