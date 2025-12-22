# Dependencies (v0.1)

This file documents major third-party packages used in v0.1 and why.
Selections are intended to be compatible with commercial use (permissive OSS licenses).

## Core runtime (backend)
- FastAPI: API framework.
- Uvicorn: ASGI server for dev/prod.
- Pydantic / pydantic-settings: schema validation + typed config.
- HTTPX: async HTTP client (LLM + Tavily calls if not using SDK).
- tenacity: retries/backoff around provider calls.
- orjson: fast JSON encoding/decoding (used for SSE payloads).

## Data layer
- PostgreSQL: system of record.
- SQLAlchemy: ORM/query layer.
- Alembic: schema migrations.
- asyncpg: Postgres driver (permissive, default in DATABASE_URL).
- pg8000: optional pure-Python driver (select via DATABASE_URL).

## Agent orchestration + structured extraction
- LangGraph: stateful graph workflows for the per-turn orchestration graph.
- Instructor: strict structured outputs for extraction (entities/facts/grounding packs).

## LLM provider access
- LiteLLM: provider-agnostic external LLM calls (used for roleplay, coaching, and extraction).

## Web grounding (internet search RAG)
- tavily-python: Tavily SDK (MIT), used for search (with retry + cache).
- (optional) LangChain Tavily integration if you later want LC tool wrappers.

## Observability
- Langfuse: traces + prompt/version tracking (OSS features in v0.1).

## UI
- Streamlit: workbench UI + internal admin tool.

## Developer tooling

- **pytest / pytest-asyncio**: pytest: automated tests (“does X still work after we change Y?”) pytest-asyncio: makes it easy to test async FastAPI/async DB code.

- **ruff**: lint/format.  Ultra-fast linter/formatter (keeps code style consistent automatically).

- **mypy**: typing. Type checker (catches bugs early when you use type hints).

- **pre-commit**: consistent checks. Runs ruff/mypy/tests automatically before commits so PRs don’t break main.
