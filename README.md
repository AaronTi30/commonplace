# commonplace

Local-first semantic search and grounded Q&A (RAG) over any public-domain text.

**Stack:** FastAPI · Next.js · PostgreSQL + pgvector · Ollama · sentence-transformers · Alembic 

---

## Why I built this

A [commonplace book](https://en.wikipedia.org/wiki/Commonplace_book) is a personal notebook of collected passages — a tool for actually retaining what you read. I wanted a digital version: ingest a book, search it semantically, ask it questions, and get answers I can *verify*.

The problem with just asking an LLM about a book is that it either hallucinates quotes, vaguely gestures at the text, or confidently cites passages that don't exist. I wanted something that couldn't do that.

So I built around a hard constraint: **every claim in an answer must be backed by a verbatim quote from a real retrieved passage, validated server-side**. If the model can't ground a claim in actual text, it says "Insufficient evidence" rather than confabulating. This makes the system less impressive-sounding on shallow questions and genuinely useful for everything else.

The other constraint was cost. Public-domain books are free. Paying per-query to search your own library made no sense — so the entire stack runs locally: embeddings via `sentence-transformers`, generation via Ollama, vectors stored in Postgres with pgvector.

---

## What it does

- **Ingest works** from Gutenberg IDs or Wikisource URLs — background job with idempotent pipeline and live progress tracking
- **Search passages** with pgvector cosine similarity, filters (author, language, source type), and copyable citations
- **Ask questions (RAG)** in two modes:
  - **Strict mode** — structured JSON claims with server-side quote-grounding validation; returns "Insufficient evidence" rather than hallucinating
  - **Fluent mode** — prose with `[N]` citation markers mapped to an evidence panel
- **Delete works** from the corpus via the UI

---

## Architecture

```
┌─────────────┐    POST /api/ingest     ┌──────────────────────────────────────────────┐
│  Next.js UI │ ──────────────────────► │  FastAPI                                     │
│             │    GET /api/jobs/{id}   │                                              │
│  TanStack   │ ◄────────────────────── │  Ingest  ──►  Worker  ──►  Chunker           │
│  Query      │    POST /api/search     │                       ──►  Embedder (MiniLM) │
│             │ ──────────────────────► │                       ──►  pgvector          │
│             │    POST /api/ask        │                                              │
│             │ ──────────────────────► │  Retriever ──► Ollama (Mistral)             │
└─────────────┘                         │            ──► Quote validator               │
                                        └──────────────────────────────────────────────┘
                                                         │
                                               PostgreSQL + pgvector
```

**Key design decisions:**

- **Postgres + pgvector over a managed vector DB** — single service, zero extra cost, full SQL for filters and joins, good enough at MVP scale
- **DB-backed job queue** (`FOR UPDATE SKIP LOCKED`) over Celery/Redis — one fewer infrastructure dependency; Postgres is already in the stack; idempotent stages make retries safe without a separate broker
- **Server-side quote grounding** — the LLM must emit a verbatim quote substring; the server validates it against `cleaned_text` after Unicode normalization. One auto-repair attempt before returning "Insufficient evidence." The LLM can't self-police this reliably, so the server does it
- **Dependency-injected encoder and Ollama client** — lets tests swap in fixed unit vectors and a fake LLM without monkeypatching; fast, deterministic CI with no model loading

---

## Repo layout

```
apps/
  api/          FastAPI backend (Python)
    app/
      api/      HTTP route handlers
      db/       SQLAlchemy models + Alembic migrations
      ingest/   Fetchers, chunker, embedder, metadata
      llm/      Ollama client, grounding validator, prompts
      worker/   Background job orchestration
  web/          Next.js frontend (TypeScript)
    src/
      app/      App Router pages (corpus, search, ask, work detail)
      components/
      lib/      Typed API client, TanStack Query setup
```

---

## Prerequisites

- Docker (Postgres + pgvector)
- Python 3.11+
- Node.js 20+
- [Ollama](https://ollama.com) (local LLM runtime)

---

## Quickstart

End-to-end demo: **ingest → search → ask → delete**.

### 1. Start Postgres

```bash
docker compose up -d
```

Create a test DB (for pytest isolation):

```bash
docker exec -it commonplace-db-1 psql -U postgres -c "CREATE DATABASE commonplace_test;"
```

### 2. Start Ollama

Install Ollama, then pull a model:

```bash
ollama pull mistral
```

### 3. Run the API and worker

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/commonplace'
export TEST_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/commonplace_test'

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd apps/api && source .venv/bin/activate
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/commonplace'
python -m app.worker.worker
```

### 4. Run the web app

```bash
cd apps/web
npm install
npm run dev
```

Open `http://127.0.0.1:3000`.

If your API is not at `http://127.0.0.1:8000`, create `apps/web/.env.local`:

```
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### 5. Try it

1. Go to **Corpus** and ingest Gutenberg `1342` (Pride and Prejudice) or `84` (Frankenstein)
2. Wait for the job to complete (live progress bar)
3. Go to **Search** — try `elizabeth` or `darcy`
4. Go to **Ask** — try "How does Elizabeth feel about Wickham?" in fluent mode; watch the evidence panel highlight the retrieved passages
5. Try strict mode — valid questions return grounded JSON claims; questions the model can't ground return "Insufficient evidence" instead of a hallucination
6. Delete a work from the Corpus page

---

## Tests

```bash
cd apps/api
source .venv/bin/activate
export TEST_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/commonplace_test'
pytest
```

Tests use real Postgres (not mocks) with per-test truncation. The encoder and Ollama client are dependency-injected and swapped for deterministic fakes in CI — no live model needed.

---

## Development

```bash
docker compose up -d      # start DB
docker compose down       # stop DB
alembic upgrade head      # apply migrations
alembic revision --autogenerate -m "description"  # new migration
```
