# Negotiation Companion Implementation

This package contains the Python implementation of the Negotiation Companion
application described in the project documentation. It uses FastAPI for the
HTTP API, SQLAlchemy for persistence, Pydantic for request/response models
and Streamlit for a simple prototype UI. The code follows the design
principles laid out in the Markdown specifications: modular services, clear
separation of concerns, descriptive identifiers and type hints throughout.

## Contents

* `api/` — FastAPI application (`main.py`) and routers for sessions,
  knowledge graph and templates. Dependencies for database sessions and
  authentication are provided in `dependencies.py`.
* `core/` — Configuration (`config.py`), database setup (`db.py`), ORM
  models (`models.py`), Pydantic schemas (`schemas.py`), event logging
  (`events.py`) and domain services (`services/`).
* `ui/` — A minimal Streamlit prototype that demonstrates how to
  interact with the API.
* `tests/` — A couple of asynchronous tests that exercise critical
  flows: creating sessions, exchanging messages and committing memory
  reviews.

## Running Locally

1. Install dependencies using Poetry:

   ```bash
   poetry install --with dev,llm,agents,ui,observability,search
   ```

2. Create a `.env` file based on `.env.example` and adjust the
   environment variables. For local development the default SQLite
   database URL is sufficient.

3. Run database migrations or initialise the schema in development
   mode. The API will automatically create the schema when started in
   `dev` or `test` environments. To run migrations manually:

   ```bash
   poetry run alembic upgrade head
   ```

4. Start the API server:

   ```bash
   poetry run uvicorn src.negot.api.main:app --reload --port 8000
   ```

5. (Optional) Run the Streamlit UI:

   ```bash
   poetry run streamlit run src/negot/ui/app.py
   ```

6. Run the test suite:

   ```bash
   poetry run pytest -q
   ```

## Extending

This MVP includes only the core flows and stubs out complex functionality
such as LLM orchestration and web search. To extend the system you can:

* Implement structured extraction of facts using `instructor` and your
  preferred language model.
* Replace the heuristic template selector with an LLM classifier.
* Integrate Tavily search by providing an API key and expanding the
  synthesis logic.
* Flesh out the knowledge graph service with CRUD endpoints for facts
  and relationships.
* Add richer safety filters as described in `docs/SAFETY.md`.