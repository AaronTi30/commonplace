# Commonplace

A **full-stack, local-first RAG (Retrieval-Augmented Generation) system** for semantic search and grounded question answering over long-form texts.

Runs entirely locally using vector search and a local LLM, with **citation-backed answers and optional strict grounding validation**.

---

## ⚡ What It Does

* 🔍 Semantic search over ingested documents
* 💬 Ask questions grounded in source text
* 📚 Returns answers with **citations and supporting quotes**
* 🧠 Optional **strict mode** to enforce evidence-backed responses
* 🔒 Fully local — no external APIs required

---

## 🧠 Key Idea

Most LLM systems hallucinate because they generate without constraints.

This system:

* retrieves relevant context first
* forces answers to be grounded in real text
* validates outputs when strict mode is enabled

---

## 🏗️ System Overview

Core pipeline:

1. **Ingestion**

   * Load and clean documents (e.g. public-domain books)

2. **Chunking**

   * Split text into retrieval-friendly segments

3. **Embedding**

   * Convert text into vector representations

4. **Indexing**

   * Store embeddings in a vector database (pgvector)

5. **Retrieval**

   * Perform similarity search (top-K)

6. **Generation**

   * Inject retrieved context into prompt
   * Generate answer using a local LLM

7. **Grounding Validation (Strict Mode)**

   * Enforce structured outputs
   * Validate claims against retrieved text
   * Return *“Insufficient evidence”* if unsupported

---

## 🧠 Grounding Modes

### Fluent Mode

* Natural language answers
* Includes citations

### Strict Mode

* Structured outputs
* Quote-level validation
* Rejects unsupported answers

---

## 🖥️ Features

* Local-first LLM inference (via Ollama)
* Vector search with pgvector
* Document ingestion + management
* Semantic search + Q&A interface
* Grounded responses with citations
* Strict validation mode for correctness

---

## 🔧 Design Goals

* Local-first (privacy + zero API cost)
* Low-latency retrieval
* Grounded, verifiable outputs
* Modular and extensible system design

---

## 📌 Why This Project

This project explores:

* how to build **reliable RAG systems locally**
* how to **reduce hallucinations through validation**
* how retrieval design impacts LLM behavior

## Prerequisites

- Docker (Postgres + pgvector)
- Python 3.11+
- Node.js 20+
- Ollama (local LLM runtime)

## Repo layout

- `apps/api`: FastAPI backend (Python)
- `apps/web`: Next.js frontend (TypeScript)

## Quickstart (local MVP demo)

This is a tight end-to-end demo script: **ingest → search → ask → delete**.

### 1) Start Postgres (+ pgvector)

```bash
docker compose up -d
```

Create a separate test DB (for pytest safety):

```bash
docker exec -it commonplace-db-1 psql -U postgres -c "CREATE DATABASE commonplace_test;"
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

export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/commonplace'
export TEST_DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/commonplace_test'  # must end with _test

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd apps/api
source .venv/bin/activate
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/commonplace'
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

### 5) Demo walkthrough (in the UI)

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

- `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/commonplace`

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

