# RouteMuse

RouteMuse is a personalized outdoor route discovery and planning application. This repository is the production-oriented scaffold: it establishes domain boundaries and a runnable planner shell without pretending that Strava, routing, scoring, or LLM features work.

## Architecture

The modular monolith consists of a Next.js/TypeScript frontend, FastAPI/Pydantic backend, and PostgreSQL with PostGIS. RouteMuse owns its normalized activity taxonomy. Deterministic geospatial providers will own route facts; deterministic application code will analyze and score; Ollama will only explain structured, provider-grounded candidates. See [the architecture decision document](docs/architecture.md).

## Repository structure

```text
backend/       FastAPI API, domain models, provider protocols, Alembic
frontend/      Next.js App Router planner shell and typed API client
docs/          Architecture documentation
.github/       Backend and frontend CI
Makefile
```

## Local setup (without Docker)

Requirements: Python 3.12, Node.js 20, and a locally available PostgreSQL instance with PostGIS. Create the database and credentials represented by `DATABASE_URL` before applying migrations.

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -e 'backend[dev]'
cd frontend
npm install
npm run dev
```

Running `npm run dev` from `frontend` starts both the Next.js development server and the FastAPI development server. The command stops both processes together. The UI is available at `http://localhost:3000`; API health is at `http://localhost:8000/health`.

In a second terminal with the virtual environment active, apply migrations with `make migrate`. The initial migration enables PostGIS. Because RouteMuse does not currently ship container configuration, PostgreSQL/PostGIS must already be running locally.

## Configuration

Active variables are `DATABASE_URL`, `CORS_ORIGINS`, and `NEXT_PUBLIC_API_BASE_URL`. `.env.example` also documents secret-free placeholders for future Strava, Ollama, and openrouteservice adapters. Ollama is not launched or downloaded by the application. Never commit `.env`.

## Commands

| Command | Purpose |
|---|---|
| `make dev` | Start the frontend and backend development servers through the frontend configuration |
| `make test` | Run backend and frontend unit tests |
| `make lint` | Run Ruff and ESLint |
| `make migrate` | Apply Alembic migrations to the configured local database |
| `cd frontend && npm run dev` | Start both Next.js and FastAPI directly from the frontend directory |

## Current limitations and next integrations

This scaffold has no authentication, persistence schema, Strava connection/import, route discovery/generation, athlete analysis, recommendation ranking, GPX, or Ollama inference. Planning controls are intentionally disabled and recommendations are empty. Next, implement Strava OAuth and a provider-payload-to-RouteMuse normalization boundary, with encrypted token handling and deterministic fixture tests. Subsequent PRs can add activity persistence/analysis, then factual geospatial adapters and deterministic candidate scoring before any LLM explanation layer.
