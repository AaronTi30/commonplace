# philosophia-engine

Monorepo for a philosophy-focused RAG + semantic search MVP.

## Prerequisites

- Docker (Postgres + pgvector)
- Python 3.11+
- Node.js 20+
- Ollama (local LLM runtime)

## Repo layout

- `apps/api`: FastAPI backend (Python)
- `apps/web`: Next.js frontend (TypeScript)

## Quickstart (smoke run)

This is the “demo script” to prove ingest → search → ask works end-to-end.

### 1) Start Postgres (+ pgvector)

```bash
docker compose up -d
```

Create a separate test DB (for pytest safety):

```bash
docker exec -it philosophia-engine-db-1 psql -U postgres -c "CREATE DATABASE philosophia_test;"
```

### 2) Start Ollama + pull a model

Install/run Ollama, then:

```bash
ollama pull mistral
```

### 3) Run API + worker

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/philosophia'
export TEST_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/philosophia_test'  # must end with _test

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd apps/api
source .venv/bin/activate
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/philosophia'
python -m app.worker.worker
```

### 4) Run web

```bash
cd apps/web
npm install
npm run dev
```

Open `http://127.0.0.1:3000`.

If your API is not at `http://127.0.0.1:8000`, create `apps/web/.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Restart `npm run dev` after changing env.

### 5) Smoke test in the UI

- Go to **Corpus** and ingest Gutenberg `1342` (Pride and Prejudice) or `84` (Frankenstein).
- Wait for the job to complete.
- Use **Search** for a character name (e.g. `elizabeth` / `darcy`).
- Use **Ask** in fluent mode and verify citations highlight evidence.
- Use **Delete** to remove a work from the corpus.

## Development (details)

```bash
docker compose up -d
docker compose down
```

Set:

- `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/philosophia`

### API

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
python -m app.worker.worker
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

