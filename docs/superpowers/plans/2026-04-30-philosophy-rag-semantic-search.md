# Philosophy RAG Semantic Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a polished full-stack, local-first semantic search + RAG app for philosophical/religious texts with in-app corpus building from Gutenberg + Wikisource, passage-level retrieval, and strict/fluent answer modes with citations.

**Architecture:** Next.js UI + FastAPI API + DB-backed worker using a Postgres job queue, Postgres+pgvector for storage/retrieval, local embeddings (sentence-transformers) and local answering (Ollama). Docker Compose runs infra (Postgres/pgvector).

**Tech Stack:** Next.js (React, TypeScript), shadcn/ui + Tailwind, TanStack Query, FastAPI (Python), SQLAlchemy + Alembic, Postgres + pgvector, Docker Compose, Ollama, sentence-transformers, pytest.

---

## Repo + file structure (locked)

**Create:**
- `README.md`
- `.gitignore`
- `docker-compose.yml`
- `apps/web/` (Next.js)
  - `apps/web/package.json`
  - `apps/web/next.config.*`
  - `apps/web/src/app/(routes)/corpus/page.tsx`
  - `apps/web/src/app/(routes)/search/page.tsx`
  - `apps/web/src/app/(routes)/ask/page.tsx`
  - `apps/web/src/app/(routes)/works/[workId]/page.tsx`
  - `apps/web/src/lib/api.ts`
  - `apps/web/src/lib/queryClient.ts`
  - `apps/web/src/components/*` (search results, evidence panel, etc.)
- `apps/api/` (FastAPI + worker)
  - `apps/api/pyproject.toml` (or `requirements.txt`)
  - `apps/api/alembic.ini`
  - `apps/api/alembic/` (Alembic scripts)
    - `apps/api/alembic/env.py`
    - `apps/api/alembic/versions/` (migration revisions live here)
  - `apps/api/app/main.py`
  - `apps/api/app/settings.py`
  - `apps/api/app/db/` (engine/session/base)
  - `apps/api/app/db/models.py`
  - `apps/api/app/api/` (routers: ingest, jobs, works, search, ask)
  - `apps/api/app/ingest/` (fetchers, parsers, chunker, embedder)
  - `apps/api/app/llm/` (Ollama client + prompts)
    - `apps/api/app/llm/ollama_client.py`
    - `apps/api/app/llm/prompts.py`
  - `apps/api/app/worker/worker.py`
  - `apps/api/tests/` (pytest)
    - `apps/api/tests/conftest.py` (FastAPI test client + DB fixtures)

**Notes:**
- Keep code split by responsibility (API vs ingest pipeline vs worker vs DB).
- Pin embeddings model: `sentence-transformers/all-MiniLM-L6-v2` (384 dims).

---

## Shared conventions (apply everywhere)

- **IDs**: use UUIDs for `work_id`, `passage_id`, `job_id`, `source_id`, artifact IDs.
- **Error shape** (API): `{ "error": { "code": string, "message": string, "details"?: any } }`
- **Filter semantics**: AND across fields; OR within arrays.
- **Defaults**:
  - Search `k`: default 10, max 50
  - Ask `k`: default 5, max 20
  - Works passage pagination: `limit` default 50, max 200
- **Strict-mode**: LLM must emit structured JSON; server validates quotes; two attempts max; fall back to “Insufficient evidence”.
- **Worker retry**: always restart from Fetch; stages are idempotent.
- **Leasing constants**: `LEASE_TTL=300s`, `MAX_RETRIES=3`

---

## Commands (copy/paste)

### Infra
- Start DB: `docker compose up -d`
- Stop DB: `docker compose down`
- View logs: `docker compose logs -f`

### API
- Install: `cd apps/api && python -m venv .venv && source .venv/bin/activate && pip install -U pip && pip install -e ".[dev]"`
- Run tests: `cd apps/api && source .venv/bin/activate && pytest -q`
- Run migrations: `cd apps/api && source .venv/bin/activate && alembic upgrade head`
- Run API: `cd apps/api && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000`
- Run worker: `cd apps/api && source .venv/bin/activate && python -m app.worker.worker`

### Web
- Install: `cd apps/web && npm install`
- Run web: `cd apps/web && npm run dev`

### Local LLM (Ollama)
- Ensure Ollama works: `ollama list`
- Pull a default model (once): `ollama pull mistral`

---

## Risks & mitigations (do early)
- **Wikisource parsing variability**: start with English Wikisource only (`en.wikisource.org`) + REST HTML endpoint; pin deterministic HTML→text rules; add fixture-based tests for extraction/chunking.
- **pgvector on Apple Silicon**: confirm an ARM64-compatible image early; if `pgvector/pgvector` fails, fall back to official Postgres + manual extension install (document in README).
- **Licensing/provenance**: enforce source restrictions (Gutenberg + Wikisource only for MVP), store `license_notes` and show source links in UI; add API tests that `source_type`, `locator`, and `canonical_url` are always present on `GET /api/works` results.

---

## Spec endpoint checklist (MVP)
- **`POST /api/ingest`**: `apps/api/app/api/ingest.py` + `apps/api/tests/test_ingest_dedupe_rules.py` — Task 10
- **`GET /api/jobs/{job_id}`**: `apps/api/app/api/jobs.py` + `apps/api/tests/test_jobs_api.py` — Task 10
- **`GET /api/works`**: `apps/api/app/api/works.py` + `apps/api/tests/test_works_api.py` — Task 10
- **`GET /api/works/{work_id}`**: `apps/api/app/api/works.py` + `apps/api/tests/test_works_api.py` — Task 10
- **`POST /api/search`**: `apps/api/app/api/search.py` + `apps/api/tests/test_search_api.py` — Task 11
- **`POST /api/ask`**: `apps/api/app/api/ask.py` + `apps/api/tests/test_ask_strict_validation.py` — Task 12

---

## Task 1: Bootstrap repo + tooling

**Files:**
- Create: `README.md`, `.gitignore`
- Create: `apps/web/*`, `apps/api/*`

- [ ] **Step 1: Initialize Node + Python project skeletons**
- [ ] **Step 2: Add `.gitignore`**
  - Include: `node_modules/`, `.next/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.env`, `.env.*`, `.DS_Store`, `*.sqlite`, `apps/api/.mypy_cache/`
- [ ] **Step 3: Create `README.md` with local dev steps**
  - Include: Docker requirement, Ollama requirement, how to run API + web, how to ingest a Gutenberg ID.
- [ ] **Step 4: Add basic formatting/linting**
  - Web: eslint + prettier (Next defaults)
  - API: ruff + black (optional but recommended)

- [ ] **Step 5: Commit**

---

## Task 2: Docker Compose for Postgres + pgvector

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**
  - Postgres image with pgvector enabled (use `pgvector/pgvector` image or Postgres + extension install).
  - Expose port `5432`
  - Volume for persistence
  - Env vars: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- [ ] **Step 2: Verify pgvector available**
  - NOTE: extension creation should be automated via Alembic migration (Task 4); this manual check is just to confirm the image supports it.
- [ ] **Step 3: Commit**

---

## Task 3: FastAPI app skeleton + settings + health

**Files:**
- Create: `apps/api/app/main.py`, `apps/api/app/settings.py`
- Create: `apps/api/app/api/__init__.py`
- Create: `apps/api/tests/test_health.py`
- Create: `apps/api/tests/conftest.py`

- [ ] **Step 1: Write failing test for health endpoint**

```python
def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to see it fail**
  - Run: `pytest -q`
  - Expected: FAIL (endpoint missing)
- [ ] **Step 2a: Add test client fixture + TEST_DATABASE_URL guard**
  - `apps/api/tests/conftest.py` provides a FastAPI `client` fixture.
  - At conftest import time, read `TEST_DATABASE_URL` from env; raise a clear error and refuse to run if it is missing or if the database name does not end with `_test`. This guard must be in place before any test that touches the DB — do not defer it to Task 4a.
- [ ] **Step 3: Implement `/api/health`**
- [ ] **Step 4: Run tests to pass**
- [ ] **Step 5: Commit**

---

## Task 4: Pin runtime configuration contract (DB URL)

> **Must complete before Task 5** — Alembic and the DB smoke test both need `DATABASE_URL` wired up. The `TEST_DATABASE_URL` guard in `conftest.py` was already established in Task 3; this task handles the app-side and Alembic wiring.

**Files:**
- Create: `apps/api/.env.example`
- Modify: `apps/api/app/settings.py`
- Modify: `README.md`

- [ ] **Step 1: Define `DATABASE_URL` contract**
  - Example: `postgresql+psycopg://postgres:postgres@localhost:5432/philosophia`
  - Add `TEST_DATABASE_URL` example: `postgresql+psycopg://postgres:postgres@localhost:5432/philosophia_test`
- [ ] **Step 2: Ensure Alembic reads `DATABASE_URL`**
  - `apps/api/alembic/env.py` loads env var.
- [ ] **Step 3: Document in README**
- [ ] **Step 4: Commit**

---

## Task 5: Database layer + Alembic migrations + models

**Files:**
- Create: `apps/api/app/db/base.py`, `apps/api/app/db/session.py`, `apps/api/app/db/models.py`
- Create: `apps/api/alembic.ini`, `apps/api/alembic/*` (Alembic init)
- Test: `apps/api/tests/test_db_smoke.py`

- [ ] **Step 1: Define SQLAlchemy models**
  - Tables per spec: `sources`, `source_artifacts`, `works`, `passages`, `passage_embeddings`, `ingestion_jobs`
  - Enforce:
    - Unique `(source_type, locator)`
    - Unique `works.source_id`
    - Unique `(passage_id, embedding_model)`
    - FK `passage_embeddings.passage_id` ON DELETE CASCADE
    - Add index for jobs: `(status, created_at)`
  - Add pgvector column for embeddings (384 dims).
  - Spec-required invariants (must enforce via DB constraints and/or tests):
    - `passage_embeddings.work_id` is present and MUST be set from `passages.work_id` on insert (denormalization; never updated independently)
    - `source_artifacts` stores exactly one of `raw_text` or `raw_html` per row (never both)
    - `sources.canonical_url` exists (human-facing display URL; not used as lookup key)
    - `ingestion_jobs.work_id` required + lease fields + payload + progress stage enum
- [ ] **Step 1a: Pin DB enforcement mechanisms (don’t leave to chance)**
  - Add CHECK constraint: `CHECK ((raw_text IS NULL) <> (raw_html IS NULL))` on `source_artifacts` (exactly one is non-null).
  - Enforce `passage_embeddings.work_id == passages.work_id`:
    - Prefer an INSERT path that always sets `work_id` by selecting from `passages` (single SQL statement), and add a DB trigger as a guardrail:
      - BEFORE INSERT/UPDATE on `passage_embeddings`: set `NEW.work_id := (SELECT work_id FROM passages WHERE id = NEW.passage_id)`; reject if missing.
- [ ] **Step 2: Create initial migration**
  - Include `CREATE EXTENSION IF NOT EXISTS vector;` in the first migration for reproducibility.
- [ ] **Step 3: DB smoke test**
  - Migrate up, create `vector` extension if needed, insert/select minimal rows.
- [ ] **Step 4: Commit**

---

## Task 6: Job leasing + worker loop (no ingestion yet)

**Files:**
- Create: `apps/api/app/worker/worker.py`
- Modify: `apps/api/app/db/models.py` (lease fields)
- Test: `apps/api/tests/test_job_leasing.py`

- [ ] **Step 1: Write failing leasing tests**
  - Claim returns a queued job, sets `locked_by/locked_at/lock_expires_at`, status→running
  - `FOR UPDATE SKIP LOCKED` semantics approximated via transaction tests
  - Expired running job can be reclaimed
- [ ] **Step 2: Implement lease claim function**
  - Eligibility: queued OR (running and expired)
  - On success: atomically set `status='running'`, lease fields (`locked_by/locked_at/lock_expires_at`), **and `works.ingestion_state='running'`** — all in the same transaction. This is the only place `works.ingestion_state` transitions to `running`; do not defer it to the Upsert stage.
  - Retry: set `status='queued'` with backoff; set `works.ingestion_state='failed'` (stays `failed` until the retry is claimed and flips back to `running`)
- [ ] **Step 3: Implement worker loop that polls and no-ops**
  - Just claims a job and marks succeeded (temporary)
- [ ] **Step 4: Tests pass**
- [ ] **Step 5: Commit**

---

## Task 7: Ingestion fetchers (Gutenberg + Wikisource) + source canonicalization

**Files:**
- Create: `apps/api/app/ingest/canonicalize.py`
- Create: `apps/api/app/ingest/fetch_gutenberg.py`
- Create: `apps/api/app/ingest/fetch_wikisource.py`
- Create: `apps/api/tests/test_canonicalize.py`
- Create: `apps/api/tests/test_fetchers_smoke.py` (mocked HTTP)

- [ ] **Step 1: Implement canonicalization**
  - Gutenberg: extract ID from URL or raw ID string; produce locator `"1342"`
  - Wikisource: enforce `https://en.wikisource.org/wiki/<Title>`; strip query/fragment; normalize underscores
  - Add examples from spec as tests.
- [ ] **Step 2: Implement fetchers**
  - Gutenberg: try `{id}-0.txt` then `{id}.txt`, store final URL + bytes
  - Wikisource: `api/rest_v1/page/html/{Title}` fetch
  - Tests use HTTP mocking; ensure `source_artifacts` persistence contract (raw_text/raw_html) is respected.
- [ ] **Step 3: Commit**

---

## Task 8: Normalization + chunking (deterministic) + heading heuristics

**Files:**
- Create: `apps/api/app/ingest/normalize.py`
- Create: `apps/api/app/ingest/chunk.py`
- Test: `apps/api/tests/test_chunking_determinism.py`

- [ ] **Step 1: Write deterministic chunking tests**
  - Given fixed input bytes + chunker_version, output passage list identical
  - Covers:
    - paragraph splitting on blank lines
    - merge to 900–1800 chars
    - split long paragraph at sentence boundary else hard split
    - heading heuristics (all-caps / Chapter pattern / short surrounded line)
- [ ] **Step 2: Implement normalization**
  - Gutenberg header/footer stripping
  - Wikisource HTML → text extraction deterministic (pin rules; avoid random whitespace)
- [ ] **Step 3: Implement chunker**
  - Produces `section_label`, `passage_index`, `cleaned_text`, `citation_string`
- [ ] **Step 4: Commit**

---

## Task 9: Embeddings pipeline (sentence-transformers) + pgvector insert + partial HNSW index

**Files:**
- Create: `apps/api/app/ingest/embed.py`
- Modify: migrations to include partial HNSW index for pinned model
- Test: `apps/api/tests/test_embed_idempotency.py`

- [ ] **Step 1: Implement embedder**
  - Model: `sentence-transformers/all-MiniLM-L6-v2`
  - Batch embeddings; record `embedding_model`, `embedding_dim=384`
- [ ] **Step 2: Implement idempotent insert**
  - `INSERT ... ON CONFLICT (passage_id, embedding_model) DO NOTHING`
- [ ] **Step 3: Add partial HNSW index migration**
  - `WHERE embedding_model='sentence-transformers/all-MiniLM-L6-v2'`
- [ ] **Step 4: Commit**

---

## Task 10: End-to-end ingest job implementation (worker stage orchestration)

**Files:**
- Modify: `apps/api/app/worker/worker.py`
- Modify: `apps/api/app/db/models.py` (progress schema helpers)
- Test: `apps/api/tests/test_ingest_job_happy_path.py` (mostly mocked)

- [ ] **Step 1: Write failing test for ingest orchestration calling stages in order**
- [ ] **Step 2: Implement stage function signatures (no-op bodies)**
  - `fetch_artifact(work_id)`, `chunk_work(work_id)`, `embed_passages(work_id)`, `upsert_work(work_id)`
  - Normalize is NOT a top-level stage function with a `work_id` — it is a pure in-memory transform (`normalize_text(raw: str) -> str`) called internally by `chunk_work`. It reads from the artifact in memory and passes clean text to the chunker; it does not write a new DB row.
- [ ] **Step 3: Make orchestration test pass with minimal “call order” implementation**
- [ ] **Step 4: Write failing test for progress updates per stage**
- [ ] **Step 5: Implement progress stage enum updates (`fetch|normalize|chunk|embed|upsert`)**
- [ ] **Step 6: Write failing test for `works.ingestion_state` transitions**
  - set `running` at job claim time
  - set `complete` on success (+ `ingested_at`)
  - set `failed` on any stage exception
- [ ] **Step 7: Implement state transitions**
- [ ] **Step 8: Write failing test for re-ingestion hard replace**
  - expects `DELETE FROM passages WHERE work_id=?` before inserting new passages
- [ ] **Step 9: Implement hard replace semantics**
- [ ] **Step 10: Commit**

---

## Task 11: Ingest + jobs + works API routers

**Files:**
- Create: `apps/api/app/api/ingest.py`
- Create: `apps/api/app/api/jobs.py`
- Create: `apps/api/app/api/works.py`
- Test: `apps/api/tests/test_ingest_dedupe_rules.py`

- [ ] **Step 1: Implement `POST /api/ingest`**
  - Canonicalize locator
  - Upsert source+work; set `works.ingestion_state='queued'` on new work creation
  - Dedupe rules from spec:
    - Active job (queued/running) → return existing `job_id`, HTTP `202`
    - `ingestion_state='complete'` → return `{ work_id, job_id: null }`, HTTP `200`
    - Terminal-failed (`status='failed'`, `retry_count >= MAX_RETRIES`) → create new job with `retry_count=0`, set `works.ingestion_state='queued'`, HTTP `202`
    - Non-terminal failed (job re-queued for auto-retry) → return existing `job_id`, HTTP `202`
- [ ] **Step 2: Write tests explicitly asserting HTTP 202 vs 200 for each dedupe branch**
  - Active job → 202; complete no-op → 200; terminal retry → 202
- [ ] **Step 3: Implement `GET /api/jobs/{job_id}`**
- [ ] **Step 4: Implement `GET /api/works` and `GET /api/works/{work_id}`**
  - `GET /api/works`: no pagination MVP; query params `source_type` (exact), `author`/`title` (ILIKE)
  - `GET /api/works/{work_id}`: cursor/limit pagination by `passage_index`; `limit` default 50, max 200
- [ ] **Step 5: Commit**

---

## Task 12: Retrieval API (`/api/search`) with filters

> **Note:** Tests in this task seed passages directly via DB fixture. Task 11 (Ingest API) provides the live end-to-end flow but is not required for these unit/integration tests.

**Files:**
- Create: `apps/api/app/api/search.py`
- Test: `apps/api/tests/test_search_api.py`

- [ ] **Step 1: Write failing API tests**
  - validates `k` bounds/default (default 10, max 50)
  - returns sorted results with `score` cosine similarity and stable snippet (first 300 chars trimmed to word boundary)
  - filters AND/OR semantics; `source_type` array filter
- [ ] **Step 2: Implement query embed + pgvector similarity query**
  - Enforce embedding_model pinned to `sentence-transformers/all-MiniLM-L6-v2`
- [ ] **Step 3: Commit**

---

## Task 12: Ask API (`/api/ask`) with strict + fluent modes (local Ollama)

> **Note:** Tests in this task use fake/stubbed LLM responses — no live Ollama required. Task 11 (Search) retrieval is reused; seed passages via DB fixture.

**Files:**
- Create: `apps/api/app/api/ask.py`
- Create: `apps/api/app/llm/ollama_client.py`
- Create: `apps/api/app/llm/prompts.py`
- Test: `apps/api/tests/test_ask_strict_validation.py` (use fake LLM responses)

- [ ] **Step 1: Write failing test for strict-mode JSON schema parsing**
- [ ] **Step 2: Implement strict-mode JSON schema dataclass + parser**
- [ ] **Step 3: Write failing test for quote normalization matching rules**
- [ ] **Step 4: Implement normalization function (NFC, whitespace collapse, quotes, dashes, footnote markers, case-fold)**
- [ ] **Step 5: Write failing test for strict-mode validation fail → one repair attempt**
- [ ] **Step 6: Implement “repair once” control flow + `meta.strict_validation`**
- [ ] **Step 7: Write failing test for strict-mode final failure returning standardized “Insufficient evidence”**
- [ ] **Step 8: Implement standardized failure response**
- [ ] **Step 9: Write failing test for fluent-mode `[N]` citation extraction**
- [ ] **Step 10: Implement fluent citation marker parser mapping to `retrieved_passages[N-1]`**
- [ ] **Step 11: Implement Ollama client wrapper (model env var + timeouts)**
- [ ] **Step 12: Commit**

---

## Task 13: Next.js UI scaffold + design system

**Files:**
- Create: `apps/web/*`

- [ ] **Step 1: Create Next.js app + Tailwind**
- [ ] **Step 2: Add shadcn/ui and base layout**
- [ ] **Step 3: Add TanStack Query and API client**
- [ ] **Step 4: Commit**

---

## Task 14: Corpus Builder UI (ingest + job progress + library list)

**Files:**
- Create: `apps/web/src/app/(routes)/corpus/page.tsx`
- Create: components for job cards, ingest form, work list

- [ ] **Step 1: Implement ingest form**
  - source_type selector + locator input
- [ ] **Step 2: Implement jobs polling**
  - progress bar + status pill + retry button
- [ ] **Step 3: Implement library list**
  - list works, link to detail
- [ ] **Step 4: Commit**

---

## Task 15: Search UI (filters + results + citations)

**Files:**
- Create: `apps/web/src/app/(routes)/search/page.tsx`
- Create: `SearchBar`, `Filters`, `PassageResultCard`

- [ ] **Step 1: Build search flow with debounced input**
- [ ] **Step 2: Render results with citation copy**
- [ ] **Step 3: Commit**

---

## Task 16: Ask UI (strict/fluent toggle + answer + evidence panel)

**Files:**
- Create: `apps/web/src/app/(routes)/ask/page.tsx`
- Create: `AnswerPanel`, `EvidencePanel`

- [ ] **Step 1: Implement ask form + toggle**
- [ ] **Step 2: Render answer markdown + inline citations**
- [ ] **Step 3: Evidence panel lists retrieved passages; highlight cited subset**
- [ ] **Step 4: Commit**

---

## Task 17: Work detail UI (passage pagination)

**Files:**
- Create: `apps/web/src/app/(routes)/works/[workId]/page.tsx`

- [ ] **Step 1: Fetch work + passages with cursor pagination**
- [ ] **Step 2: Render readable passage viewer**
- [ ] **Step 3: Commit**

---

## Task 18: End-to-end dev run + smoke tests

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Local smoke run**
  - Start Postgres via docker-compose
  - Start API + worker
  - Start web
  - Ingest a known Gutenberg ID (e.g., 1342) and confirm Search + Ask work
- [ ] **Step 2: Add a minimal `make dev` or scripts section in README**
- [ ] **Step 3: Commit**

---

## Plan review checklist (before execution)
- [ ] **Task 1** — Confirm pinned versions for Python + Node and document in README
- [ ] **Task 2** — Confirm `pgvector/pgvector` ARM64 image works on Apple Silicon before writing migrations; document fallback in README if not
- [ ] **Task 1 / Task 18** — Confirm Ollama installation instructions and default model (`mistral`) are clear in README

