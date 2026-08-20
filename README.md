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

## Local setup

Requirements: Python 3.12, Node.js 20, and a locally available PostgreSQL instance with PostGIS. Install PostgreSQL and the PostGIS package using the method appropriate for your operating system or database provider. The server must have the PostGIS extension binaries available; Alembic enables the extension in the RouteMuse database but cannot install those server-side files.

From the repository root, configure both applications and install their dependencies:

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -e 'backend[dev]'
npm --prefix frontend install
```

Create a database and role using your PostgreSQL administration tools, then set `DATABASE_URL` in `.env` to its SQLAlchemy psycopg URL. The example value illustrates the expected format; choose your own local credentials. After PostgreSQL is running and the PostGIS server package is installed, apply and inspect migrations:

```bash
make migrate
cd backend && alembic current
```

The initial migration runs `CREATE EXTENSION IF NOT EXISTS postgis`, so it is safe to reapply when PostGIS is already enabled. PostgreSQL may require the configured role to have permission to create extensions. Its downgrade intentionally leaves PostGIS installed: removing an extension can invalidate or destroy geospatial objects introduced later. PostgreSQL/PostGIS must already be running locally.

Start the normal development workflow from the repository root:

```bash
make dev
```

This starts Next.js and FastAPI together through the frontend's `concurrently` command. If either process exits, the command terminates the other rather than leaving an orphaned server. The UI is available at `http://localhost:3000`; API health is at `http://localhost:8000/health`. Keep the Python virtual environment active so the backend command uses the installed development dependencies.

## Configuration

Active variables are `DATABASE_URL`, `CORS_ORIGINS`, and `NEXT_PUBLIC_API_BASE_URL`. `DATABASE_URL` is the sole database connection setting and is used by both the application and Alembic. The backend and Alembic read the root `.env`; Next.js reads its process environment and optional `frontend/.env.local`. The default API URL works without extra frontend configuration. To override it, put `NEXT_PUBLIC_API_BASE_URL=...` in `frontend/.env.local` or export it before `make dev`.

`.env.example` also documents secret-free placeholders for future Strava, Ollama, and openrouteservice adapters. Those placeholders are not used yet, and Ollama is not launched or downloaded by the application. Never commit local environment files.

## Commands

| Command | Purpose |
|---|---|
| `make dev` | Start the frontend and backend development servers through the frontend configuration |
| `make test` | Run backend and frontend unit tests |
| `make lint` | Run Ruff and ESLint |
| `make migrate` | Apply Alembic migrations to the configured local database |

## Current limitations and next integrations

This scaffold has no authentication, persistence schema, Strava connection/import, route discovery/generation, athlete analysis, recommendation ranking, GPX, or Ollama inference. Planning controls are intentionally disabled and recommendations are empty. Next, implement Strava OAuth and a provider-payload-to-RouteMuse normalization boundary, with encrypted token handling and deterministic fixture tests. Subsequent PRs can add activity persistence/analysis, then factual geospatial adapters and deterministic candidate scoring before any LLM explanation layer.
