# Sales Engine

A local tool for finding, reviewing, and qualifying litigation-related sales signals.

## Tech Stack

- Frontend: React, TypeScript, Vite
- Backend: FastAPI, SQLAlchemy, Pydantic
- Database: PostgreSQL in Docker
- Runtime: Docker Compose
- Tests: Pytest

## Architecture

The frontend calls the FastAPI backend. The backend searches public legal sources, optionally scrapes source pages, extracts structured signal data, scores each signal, and stores results in PostgreSQL.

Main flow:

```text
Discovery Run
-> Search providers
-> Scraping providers
-> Signal extraction
-> Quality scoring
-> Daily Triggers
-> Opportunities
```

## How to Use

1. Copy the environment template:

```bash
cp backend/.env.example backend/.env
```

2. Add any optional API keys in `backend/.env`.

3. Start the app:

```bash
docker compose up --build
```

4. Open the app:

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs

5. In the app, run **Discovery Runs**, review the results, convert useful signals into opportunities, and work the best items from **Daily Triggers**.

## Environment APIs

Set these in `backend/.env` as needed:

```env
TAVILY_API_KEY=
FIRECRAWL_API_KEY=
OPENAI_API_KEY=
GROQ_API_KEY=
GEMINI_API_KEY=
COURTLISTENER_API_KEY=
```

- `TAVILY_API_KEY`: live web search for discovery runs.
- `FIRECRAWL_API_KEY`: richer page extraction when normal HTTP scraping is limited.
- `OPENAI_API_KEY`: structured extraction from scraped/source text.
- `GROQ_API_KEY`: alternative structured extraction provider when no OpenAI key is available.
- `GEMINI_API_KEY`: final quality judgment for whether a signal is worth pursuing.
- `COURTLISTENER_API_KEY`: optional authenticated CourtListener access; public access can still work without it.

## Local Checks

Backend:

```bash
cd backend
python -m pytest
```

Frontend:

```bash
cd frontend
npm run build
```
