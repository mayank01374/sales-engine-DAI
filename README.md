# Sales Engine

A local sales workspace for finding, reviewing, qualifying, and converting litigation-related public signals into sales opportunities.

## Stack

- Frontend: React, TypeScript, Vite
- Backend API: FastAPI, SQLAlchemy, Pydantic
- Background jobs: Celery worker
- Queue/cache: Redis
- Database: PostgreSQL in Docker
- Migrations: Alembic
- Runtime: Docker Compose
- Tests: Pytest

## Architecture

The app runs as four Docker Compose services:

- `frontend`: Vite React app on `http://localhost:5173`
- `backend`: FastAPI API on `http://localhost:8000`
- `worker`: Celery worker that runs web discovery jobs
- `postgres` and `redis`: persistence and job broker/result backend

Backend startup runs database migrations before serving the API:

```text
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The discovery path is:

```text
Discovery Run request
-> Celery job
-> Query builder + source packs
-> Search providers
   -> CourtListener
   -> Tavily when configured
   -> local fallback when Tavily is not configured
-> Scraping providers
   -> Firecrawl when configured
   -> raw HTTP scraper with robots.txt checks
   -> optional Playwright scraper
-> Extract structured signal facts
   -> Groq if configured
   -> OpenAI if configured and Groq is not configured
   -> deterministic fallback extractor otherwise
-> Score and gate signal quality
-> Daily Triggers
-> Convert accepted signals into Opportunities
```

Important backend modules:

- `backend/app/main.py`: FastAPI app, routers, startup seed hook
- `backend/app/models.py`: SQLAlchemy models
- `backend/app/services/__init__.py`: core opportunity, scoring, import/export, and seed services
- `backend/app/services/web_search/`: search providers
- `backend/app/services/scraping/`: source scraping providers
- `backend/app/services/web_discovery/`: discovery runner, extraction, dedupe, quality gate, source packs
- `backend/app/routers/`: API endpoints
- `backend/alembic/versions/`: database migrations

## Main Product Areas

- Daily Triggers: high-quality, non-stale, non-rejected signals that pass the quality gate.
- Discovery Runs: raw discovery jobs and review tabs for passed, failed, duplicate, rejected, and converted signals.
- Opportunities: converted matters for sales follow-up.
- Settings: quality thresholds, source allow/block lists, source packs, discovery defaults, date policy, and Gemini status.

## Quality Gate

Signals are scored on:

- confidence
- source quality
- discovery pain
- product fit
- sales actionability
- final trigger score

The gate also checks:

- whether the item is an actionable litigation or investigation trigger
- stale or unknown signal dates
- blocked sources
- missing parties or missing source evidence
- duplicate opportunities

Settings from the UI are persisted in `scoring_config` and applied during scoring. `allow_unknown_signal_date` controls whether unknown-date signals can pass. `trusted_domains` and `blocked_domains` influence source classification.

## CourtListener Dates

CourtListener discovery uses root date fields such as `dateFiled` and also nested RECAP document fields such as `recap_documents[].entry_date_filed`. The provider uses the newest available filing date so docket results do not become `unknown` when the date is only present on a matched RECAP document.

## Setup

1. Copy the environment template:

```bash
cp backend/.env.example backend/.env
```

2. Add optional API keys in `backend/.env`.

3. Start the stack:

```bash
docker compose up --build
```

4. Open:

- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## Environment Variables

Core:

```env
DATABASE_URL=
CORS_ORIGINS=
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
LOG_LEVEL=
```

Provider keys:

```env
TAVILY_API_KEY=
FIRECRAWL_API_KEY=
OPENAI_API_KEY=
GROQ_API_KEY=
GEMINI_API_KEY=
COURTLISTENER_API_KEY=
```

Discovery and quality:

```env
WEB_DISCOVERY_MAX_RESULTS=
WEB_DISCOVERY_RATE_LIMIT_SECONDS=
SCRAPING_USER_AGENT=
WEB_DISCOVERY_USE_PLAYWRIGHT=
ENABLE_DEMO_DATA=
ENABLE_FORCE_CONVERT=
DAILY_TRIGGER_THRESHOLD=
MIN_CONFIDENCE_SCORE=
MIN_SOURCE_QUALITY_SCORE=
MIN_DISCOVERY_PAIN_SCORE=
MIN_DCOVER_FIT_SCORE=
MIN_SALES_ACTIONABILITY_SCORE=
MAX_SIGNAL_AGE_DAYS=
MAX_PER_SOURCE_DOMAIN=
MAX_PER_TRIGGER_CATEGORY=
MAX_PER_SAME_PARTY=
SOURCE_ALLOWLIST=
SOURCE_BLOCKLIST=
DISCOVERY_QUERY_SETTINGS=
```

Notes:

- `TAVILY_API_KEY` enables live web search beyond CourtListener.
- `FIRECRAWL_API_KEY` enables richer page extraction before falling back to raw HTTP.
- `GROQ_API_KEY` is preferred for structured extraction when present.
- `OPENAI_API_KEY` is used for structured extraction when Groq is not configured.
- `GEMINI_API_KEY` enables the final Gemini pursue/do-not-pursue judgment.
- `COURTLISTENER_API_KEY` is optional; public CourtListener access can still work without it.
- `ENABLE_FORCE_CONVERT=true` allows converting signals that fail the quality gate.

## Local Checks

Backend:

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest tests
```

Frontend:

```bash
cd frontend
npm run build
```

Alembic:

```bash
cd backend
.\.venv\Scripts\python.exe -m alembic heads
```
