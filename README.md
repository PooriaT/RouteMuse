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
docker-compose.yml
Makefile
```

## Local setup

Requirements: Docker with Compose (recommended), or Python 3.12 and Node 20.

```bash
cp .env.example .env
make dev
# UI: http://localhost:3000
# API health: http://localhost:8000/health
```

Run `make migrate` in another terminal to apply the PostGIS migration. `make down` stops the stack. For host development, install `backend` with `pip install -e 'backend[dev]'`, run `uvicorn app.main:app --reload` from `backend`, then run `npm install && npm run dev` from `frontend`.

## Configuration

Active variables are `DATABASE_URL`, `CORS_ORIGINS`, and `NEXT_PUBLIC_API_BASE_URL`. `.env.example` also documents secret-free placeholders for future Strava, Ollama, and openrouteservice adapters. Ollama is not launched or downloaded by Compose. Never commit `.env`.

## Commands

| Command | Purpose |
|---|---|
| `make dev` | Build and start frontend, backend, and PostGIS |
| `make test` | Run backend and frontend unit tests |
| `make lint` | Run Ruff and ESLint |
| `make migrate` | Apply Alembic migrations inside Compose |
| `make down` | Stop local services |

## Current limitations and next integrations

This scaffold has no authentication, persistence schema, Strava connection/import, route discovery/generation, athlete analysis, recommendation ranking, GPX, or Ollama inference. Planning controls are intentionally disabled and recommendations are empty. Next, implement Strava OAuth and a provider-payload-to-RouteMuse normalization boundary, with encrypted token handling and deterministic fixture tests. Subsequent PRs can add activity persistence/analysis, then factual geospatial adapters and deterministic candidate scoring before any LLM explanation layer.
