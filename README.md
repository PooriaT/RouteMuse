# RouteMuse

RouteMuse is a personalized outdoor route discovery and planning application. This repository establishes domain boundaries and a runnable planner shell. Its backend supports a secure Strava account connection, historical activity synchronization, and deterministic athlete-profile analysis, and provider-grounded walking and hiking routing, with deterministic, transparent personalized scoring and diversity selection. LLM explanations remain intentionally unimplemented.

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

Requirements: Python 3.13, Poetry 2.x, Node.js 20, npm, and a locally available PostgreSQL instance with PostGIS. Install PostgreSQL and the PostGIS package using the method appropriate for your operating system or database provider. The server must have the PostGIS extension binaries available; Alembic enables the extension in the RouteMuse database but cannot install those server-side files.

From the repository root, configure both applications and install their dependencies:

```bash
cp .env.example .env
cd backend
poetry env use python3.13
poetry install
cd ..
npm --prefix frontend ci
```

Create a database and role using your PostgreSQL administration tools, then set `DATABASE_URL` in `.env` to its SQLAlchemy psycopg URL. The example value illustrates the expected format; choose your own local credentials. After PostgreSQL is running and the PostGIS server package is installed, apply and inspect migrations:

```bash
make migrate
cd backend && poetry run alembic current
```

The initial migration runs `CREATE EXTENSION IF NOT EXISTS postgis`, so it is safe to reapply when PostGIS is already enabled. PostgreSQL may require the configured role to have permission to create extensions. Its downgrade intentionally leaves PostGIS installed: removing an extension can invalidate or destroy geospatial objects introduced later. PostgreSQL/PostGIS must already be running locally.

Start the normal development workflow from the repository root:

```bash
make dev
```

This starts Next.js and FastAPI together through the frontend's `concurrently` command. FastAPI runs in the Poetry-managed backend environment, so no virtual-environment activation is needed. If either process exits, the command terminates the other rather than leaving an orphaned server. The UI is available at `http://localhost:3000`; API health is at `http://localhost:8000/health`.

## Configuration

Active variables are `DATABASE_URL`, `CORS_ORIGINS`, `FRONTEND_URL`, `NEXT_PUBLIC_API_BASE_URL`, `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REDIRECT_URI`, `STRAVA_TOKEN_ENCRYPTION_KEY`, and `OPENROUTESERVICE_API_KEY`. Optional server-side Ollama variables are `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and `OLLAMA_REQUEST_TIMEOUT_SECONDS`. `DATABASE_URL` is the sole database connection setting and is used by both the application and Alembic. `FRONTEND_URL` is the trusted planner URL the backend redirects to after successful Strava authorization. The backend and Alembic read the root `.env`; Next.js reads its process environment and optional `frontend/.env.local`. The default URLs work without extra frontend configuration. To override the API URL, put `NEXT_PUBLIC_API_BASE_URL=...` in `frontend/.env.local` or export it before `make dev`.

To configure Strava, create an API application in Strava's developer settings and register the callback domain for the host used by `STRAVA_REDIRECT_URI`. For local development, the example callback is `http://localhost:8000/api/v1/strava/callback`; the configured redirect URI must use that callback route and a host accepted by the Strava application. Copy the client ID and client secret into the local `.env`, then generate a Fernet key for `STRAVA_TOKEN_ENCRYPTION_KEY` from the backend directory:

```bash
cd backend
poetry run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep that key stable for the lifetime of stored connections. Never commit the client secret, encryption key, or local environment files.

### Location search

Set `OPENROUTESERVICE_API_KEY` in the root `.env` to enable location search. The credential is read only by FastAPI and must never be put in a `NEXT_PUBLIC_` variable. It is validated lazily when `GET /api/v1/planning-areas/search?q=North%20Vancouver` is called, so missing geocoding configuration does not prevent startup, health checks, Strava, or the athlete profile from working.

The endpoint accepts a RouteMuse search query and bounded result limit rather than proxying provider parameters. OpenRouteService/Pelias features are reduced at the integration boundary to provider-independent `PlanningArea` values: coordinates, display name, optional supplied bounds, provider identity, and attribution. Attribution is retained and displayed with the selection. Raw responses and planning areas are not persisted. Geocoding, factual routing adapters, and deterministic round-trip candidate orchestration are implemented.

Strava configuration is validated only when a Strava endpoint is invoked, so an unconfigured provider does not prevent `/health` from starting. Begin authorization by navigating the browser to `GET /api/v1/strava/connect`. Connection state is available from `GET /api/v1/strava/status`, and `POST /api/v1/strava/disconnect` revokes the provider credential before deleting it locally.

### Strava activity synchronization

Synchronize one inclusive calendar-date range with `POST /api/v1/strava/sync`:

```json
{
  "start_date": "2026-08-01",
  "end_date": "2026-08-31",
  "timezone": "America/Vancouver"
}
```

All three fields are required. `timezone` must be an IANA timezone; there is no server-timezone fallback. RouteMuse interprets the start as local midnight and the end as inclusive through that local calendar day. It queries Strava using the corresponding UTC lower bound and the exclusive next-local-midnight upper bound, so daylight-saving transitions are preserved.

The request runs synchronously and returns page, fetch, insert, update, and unsupported-sport counts. The same summary pages persist Strava's nullable `map.summary_polyline` without per-activity detail or stream requests. RouteMuse keeps only this privacy-reduced geometry and never reconstructs hidden portions, infers home coordinates, reverse-geocodes history, or stores raw activity payloads. Activities are committed one provider page at a time and upserted by the existing connection/activity uniqueness rule. An empty range is successful. If a later page fails, the controlled error includes a `partial` synchronization result while earlier pages remain committed. Authentication, timeouts, temporary provider failures, malformed responses, and rate limits have distinct safe error codes; rate-limit responses include usable `Retry-After` metadata when Strava supplies it.

Rows imported before geometry support remain valid with null geometry; no background network backfill runs. Re-synchronize an older bounded date range to populate geometry where Strava returns it.

### Athlete profile

Build the current connected athlete's deterministic profile from already-saved
normalized activities with `POST /api/v1/athlete-profile`:

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-03-31",
  "timezone": "America/Vancouver"
}
```

The request uses the same inclusive calendar-period and IANA-timezone semantics
as Strava synchronization. It does not contact Strava. RouteMuse loads persisted
canonical activity facts for the current singleton connection, excludes
unsupported normalized kinds from supported metrics, and calculates the profile
on demand without a derived-data table.

The typed response includes the selected period, analyzed and excluded counts,
per-kind activity summaries, dominant activity with its moving-time share,
representative capability ranges and sample sizes, and per-kind
consistency/recency signals. A period with no supported activities is successful
and returns `activities_analyzed: 0`, empty summary/signal lists, and
`dominant_activity: null`. See [athlete profile metrics](docs/athlete-profile.md)
for formulas, units, percentile semantics, and missing-data behavior.

After RouteMuse confirms the saved Strava connection, the planner can display a
profile for the selected period without requiring another import. A completed
import refreshes the profile using the same period and timezone. A partial import
keeps its synchronization warning and pauses the definitive profile view until a
retry completes. That incomplete state is derived from persisted synchronization
runs, so it survives page reloads and period changes. The planner then selects a
normalized planning area, chooses or overrides the RouteMuse activity type, and
optionally accepts effort, route-shape, and novelty preferences. Display units are
converted to canonical meters and seconds before `POST /api/v1/planning/validate`.
Empty overrides remain null for future profile-driven inference. Validation itself does
not generate a route; a resolved distance can be submitted to the factual candidate endpoint.

`.env.example` documents optional Ollama configuration. Ollama must already be installed and running externally with the configured model; RouteMuse never launches Ollama or pulls models. Configuration is read only by FastAPI, so no `NEXT_PUBLIC_` Ollama variable is required. Startup, health checks, and deterministic recommendations work without Ollama, and Ollama output does not affect scoring or ranking. After diversity selection, only selected routes receive structured reasoning. Missing or failed Ollama uses the first-class deterministic, scorecard-grounded fallback and does not turn a valid recommendation request into an error.

## OpenStreetMap discovery

The backend includes a replaceable `RouteDiscoveryProvider` backed by Overpass. It
discovers factual OpenStreetMap ways and named route memberships for a planning
area; it does **not** generate or rank routed paths. Every query has an explicit
bounding box. Areas larger than a 25 km discovery radius are conservatively
clamped around the selected planning-area center.

`OVERPASS_API_URL` can select a public, commercial, or self-hosted interpreter; no
API key is required. Successful normalized results use a small process-local,
five-minute bounded cache, and a provider instance serializes its HTTP requests to
avoid parallel bursts against shared infrastructure. Returned features retain
`© OpenStreetMap contributors` attribution and the
[OpenStreetMap copyright/ODbL reference](https://www.openstreetmap.org/copyright).

## Walking and hiking routing

The OpenRouteService Directions adapter maps walking, hiking, road cycling, gravel
cycling, and mountain biking to explicit profiles. Running, trail running, and skiing
are not silently approximated. It accepts
typed waypoint or deterministic round-trip requests and reuses the server-only
`OPENROUTESERVICE_API_KEY` configuration used by geocoding.

Directions GeoJSON is normalized into canonical route geometry, actual provider
distance and duration, nullable ascent/descent, descriptive surface, way-type,
steepness and trail-difficulty breakdowns, warnings, and OpenRouteService
provenance/attribution. These facts remain provider-grounded: the adapter neither
recomputes distance nor calls a separate elevation service. Candidate ranking and
recommendation scoring are not implemented.

## Deterministic factual candidates

`POST /api/v1/route-candidates` accepts a validated `RoutePlanningRequest` with an
explicit target distance. It supports null/`LOOP` shape only and returns a typed,
ordered result containing up to four unique candidates. RouteMuse makes at most
eight sequential provider attempts using stable SHA-256-derived seeds, the repeating
target factors `1.00, 0.90, 1.10, 0.95, 1.05`, and four round-trip points. Targets
above the documented 100 km hosted-provider bound are skipped rather than sent.

Routes are projected around a shared local latitude with antimeridian unwrapping,
then resampled every 50 metres into 40-metre spatial cells with a one-cell tolerance
halo. A direction-independent Jaccard overlap of at least 0.80 is a
duplicate. Exhaustion after at least one unique route returns a partial result and
warning; zero routes is a controlled error. Rate limits, credentials/configuration,
and malformed responses stop generation immediately. No discovery provider, LLM,
ranking, persistence, or frontend map participates in this operation.

## Commands

The planner now posts its typed preferences and historical period to
`/api/v1/recommendations` and renders the response in its authoritative server rank
order as responsive recommendation cards alongside provider-grounded GeoJSON in
MapLibre GL JS. Each card presents readable route facts, complete and semantically
distinct scorecards, measured surface/way/technical characteristics, warnings,
provider attribution, and the server's local-model or deterministic-fallback
reasoning. Card and map interactions share one candidate selection, so either
surface updates the other without client-side reranking or score calculation.
Configure a replaceable basemap style with
`NEXT_PUBLIC_MAP_STYLE_URL`; when it is absent or unavailable, recommendation
generation and results remain usable while the map shows a controlled fallback.
MapLibre keeps style/source attribution visible, while the selected route's
deduplicated provider attribution is rendered separately below the map. RouteMuse
does not reroute, recalculate geometry, or rank candidates in the browser.

| Command | Purpose |
|---|---|
| `make dev` | Start the frontend and backend development servers through the frontend configuration |
| `make test` | Run backend and frontend unit tests |
| `make lint` | Run Ruff and ESLint |
| `make migrate` | Apply Alembic migrations to the configured local database |

Backend commands run through Poetry. Their direct equivalents, from `backend/`, are:

```bash
poetry run pytest
poetry run ruff check .
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload
```

## Current limitations and next integrations

RouteMuse still has no user-account system, GPX export, route editing, or route saving. Athletes can select two or three returned recommendations for an accessible, responsive side-by-side comparison of route facts, technical characteristics, existing scores, warnings, reasoning, and provider metadata; comparison never recalculates or changes the server ranking. The factual route-candidate endpoint remains deliberately unranked, while the separate recommendation endpoint applies deterministic personalized scoring to copied candidate data. Strava OAuth credentials are connected and encrypted server-side; historical activities can be synchronized idempotently, and exact `sport_type` values are normalized at the integration boundary while unsupported values remain identifiable.


### Personalized recommendations

`POST /api/v1/recommendations` takes `planning_request`, `start_date`, `end_date`,
and `timezone`. It loads saved athlete history server-side, infers a missing
distance only from matching history, generates factual routes, and returns up to
three ranked, meaningfully distinct candidates with every score assessment,
confidence component, warning, geometry, and attribution visible. Ranking is the
versioned deterministic `recommendation-v1` heuristic. An LLM cannot affect
scoring, ranking, or diversity selection, but configured Ollama may be called
after selection to produce structured reasoning; otherwise the endpoint uses its
deterministic reasoning fallback. The existing `POST /api/v1/route-candidates`
remains the unranked factual/debug API.
See [recommendation scoring](docs/recommendation-scoring.md) for formulas.
