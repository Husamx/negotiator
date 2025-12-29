# Local Setup (v0.1)

Developer-only setup.

All commands below assume you run them from the `legacy/` directory. From the
repo root, `cd legacy` first.

## Prerequisites
- Python 3.11+
- Poetry
- PostgreSQL (local or managed)

## Install
```bash
poetry install --with dev,llm,agents,ui,observability,search
```

## Environment
Copy `.env.example` to `.env` and fill required values.

## Run (backend)
```bash
poetry run uvicorn negot.api.main:app --reload --port 8000
```

## Run (Streamlit UI)
```bash
poetry run streamlit run src/negot/ui/app.py
```

## Migrations
```bash
poetry run alembic upgrade head
```
