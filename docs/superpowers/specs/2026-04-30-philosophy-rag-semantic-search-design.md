# Philosophy RAG Semantic Search — Design Spec

**Date:** 2026-04-30  
**Status:** Draft (approved in chat; pending spec review + user review)  

## Goal
Build a resume-grade full-stack application for passage-level semantic search and RAG over philosophical + religious public-domain texts. Users can build a corpus in-app from Project Gutenberg and Wikisource, search passages with citations, and ask questions with grounded, cited answers.

## Non-Goals (MVP)
- Multi-user accounts / auth
- Paid hosted model APIs
- Cloud deployment target (design assumes local dev; deploy later)
- Generic “any URL” web scraping
- Notes/bookmarks/saved queries (planned post-MVP)

## Target MVP Scale
- ~500 works (tens of thousands of passages), passage-level indexing

## Primary Product Positioning
- Polished full-stack product experience, with credible applied AI (retrieval transparency + grounded answers)

---

## High-Level Architecture

### Frontend (Next.js)
- Pages:
  - **Corpus Builder**: add texts (Gutenberg ID/URL, Wikisource URL), view ingestion jobs, view library
  - **Search**: passage search with filters + citations
  - **Ask (RAG)**: question answering grounded in retrieved passages, strict/fluent toggle
  - **Work Detail**: metadata + passage viewer (pagination)
- UX principles:
  - Always show citations + source work metadata
  - Retrieval transparency: show the exact context pack used for answers (“Evidence panel”)
  - Progress + retry UX for ingestion jobs

### Backend (FastAPI + worker)
- **FastAPI API service**: public endpoints (single-user, no auth)
- **Background worker**: ingestion pipeline implemented as jobs (DB-backed queue for MVP)
- “Production-ish” fundamentals:
  - Idempotent ingestion (same source locator doesn’t duplicate)
  - Timeouts + clear errors
  - Structured logs and timings (ingest, embed, retrieve, generate)
  - Schema migrations for reproducible setup

### Storage (Postgres + pgvector)
- Postgres is the system of record for:
  - works, passages, embeddings, ingestion jobs, provenance/license notes
- pgvector provides similarity search over passage embeddings
- Optional later: Postgres full-text for hybrid retrieval

### Local Models (no-cost runtime)
- **Embeddings**: local `sentence-transformers` model (CPU-friendly on M1)
- **Answer generation**: local instruction model via **Ollama** (or equivalent local runner)
  - Recommended default model: `mistral` (7B, good instruction-following, fits in M1 unified memory)
  - Configurable via env var `OLLAMA_MODEL` (default: `mistral`); recorded in `meta.llm_model` on every response
  - Strict-mode structured JSON output requires a model with reliable instruction-following; `mistral` is the tested baseline

### Local Development “Best Practice”
- Docker Compose for infra deps (Postgres + pgvector)
- Run Next.js + FastAPI locally for fast reload
- Run Ollama natively on macOS (often best perf on Apple Silicon)

---

## Corpus Builder Sources (MVP)

### Supported inputs
- **Project Gutenberg**: book ID or URL
- **Wikisource**: page URL

### Source fetching contract (MVP, pinned)
- **Gutenberg canonical artifact**
  - Fetch UTF-8 plain text from one of:
    - `https://www.gutenberg.org/files/{id}/{id}-0.txt` (preferred when present)
    - `https://www.gutenberg.org/files/{id}/{id}.txt` (fallback)
  - Store fetched bytes as `source_artifacts.raw_text` and record `final_url`, `content_type`, `content_sha256`.
  - Normalize by stripping standard Gutenberg header/footer boilerplate before chunking.
- **Wikisource canonical artifact**
  - Fetch rendered HTML via MediaWiki REST endpoint:
    - `https://<lang>.wikisource.org/api/rest_v1/page/html/{Title}`
  - Store fetched HTML as `source_artifacts.raw_html` and record `final_url`, `content_type`, `content_sha256`.
  - Extract main reading content and convert to text deterministically (pinned parser rules in implementation; MVP targets English Wikisource first).

### Licensing constraint
- MVP includes only texts that are public-domain / redistributable according to their source. (Some modern translations are copyrighted; ingestion UI should surface provenance + notes.)

---

## Data Model (logical)

### `sources`
Represents an upstream source + canonical locator.
- `source_type`: `gutenberg` | `wikisource`
- `locator`: normalized canonical identifier (Gutenberg: numeric ID string e.g. `"1342"`; Wikisource: canonical URL e.g. `"https://en.wikisource.org/wiki/Republic"`)
- `canonical_url`: human-facing URL for the work (Gutenberg: `https://www.gutenberg.org/ebooks/{id}`; Wikisource: same as `locator`). Stored for display/linking; not used as a lookup key.
- `license_notes` (free text)
- **Locator canonicalization (MVP, concrete):**
  - Gutenberg: extract numeric ID; canonical `locator` is the decimal string (e.g., `"1342"`).
  - Wikisource:
    - enforce `https://`
    - drop query params + fragments
    - normalize host to `en.wikisource.org` (MVP)
    - canonicalize path to `/wiki/<Title>` (spaces normalized to underscores)
    - examples:
      - `http://en.wikisource.org/wiki/Republic?oldformat=true#Book_I` → `https://en.wikisource.org/wiki/Republic`
      - `https://en.wikisource.org/wiki/Bhagavad_Gita/Chapter_1` → itself (no query/fragment)
- Timestamps: `created_at`, `updated_at`
- Unique constraint: (`source_type`, `locator`)

### `source_artifacts`
Stores fetched artifacts for provenance/debugging and to enable re-parse/re-chunk without refetching.
- `source_id` (FK)
- `retrieved_at`
- `retrieval_url`, `final_url`
- `http_status`
- `content_type`
- `content_sha256`
- `raw_text` (nullable) — populated for Gutenberg sources; NULL for Wikisource
- `raw_html` (nullable) — populated for Wikisource sources; NULL for Gutenberg
- Exactly one of `raw_text` / `raw_html` is non-NULL per artifact row; the other is always NULL
- `parser_version`
- `notes` (free text)
- Timestamps: `created_at`

### `works`
Normalized work metadata.
- `title`, `author`, `language` (best-effort)
- `source_id` (FK)
- **MVP identity rule:** one `work` per `source` (Unique constraint: `source_id`)
- `ingestion_state`: `queued` | `running` | `complete` | `failed`
- `ingested_at`
- Timestamps: `created_at`, `updated_at`

### `passages`
Atomic retrieval unit (paragraph-ish).
- `work_id` (FK)
- `section_label` (best-effort; chapter heading if detectable)
- `passage_index` (monotonic within a work)
- `raw_text`
- `cleaned_text`
- `citation_string` (stable reference user can copy)
- `chunker_version` (so chunking is deterministic and evolvable)
- Timestamps: `created_at`, `updated_at`

### `passage_embeddings`
Stores vectors per passage per embedding model.
- `passage_id` (FK → `passages.id` ON DELETE CASCADE), `work_id` (FK)
- `embedding_model` (string)
- `embedding` (pgvector column; cosine distance)
- `embedding_dim` (int; recorded for migrations/debugging)
- Unique constraint: (`passage_id`, `embedding_model`)
- **Note:** `work_id` is a deliberate denormalization (already reachable via `passage_id → passages.work_id`) to avoid a join on hot retrieval paths. It MUST be set from `passages.work_id` at insert time and is never updated independently.
- **Cascade delete:** the `ON DELETE CASCADE` on `passage_id` means deleting a `passages` row automatically removes its embeddings. Re-ingestion therefore only needs to `DELETE FROM passages WHERE work_id = ?` — the embeddings rows are removed by the cascade.

### `ingestion_jobs`
DB-backed queue.
- `job_type`: `ingest_work`
- `status`: `queued` | `running` | `succeeded` | `failed`
- `progress` (counts by stage)
- `error` (text)
- `retry_count`
- `work_id` (FK; required)
- `payload` (JSON): `{ options?: { force?: boolean } }`
- Leasing fields: `locked_at`, `locked_by`, `lock_expires_at`
- Timestamps: `created_at`, `updated_at`

---

## Ingestion Pipeline (end-to-end)

### User flow
1. User pastes Gutenberg locator (ID/URL) or a Wikisource URL into Corpus Builder.
2. Frontend calls `POST /api/ingest`.
3. Backend canonicalizes the locator, upserts `sources` + `works`, enqueues `ingestion_job(work_id=...)`, and returns `job_id` + `work_id`.
4. Worker processes stages and updates job progress for UI polling.
5. On success: work appears in library and is searchable; on failure: UI shows error + retry.

### Job leasing (MVP semantics)
Workers claim jobs via an atomic DB operation that sets a lease. A worker may only process a job if it holds the lease.

**Constants (pinned):** `LEASE_TTL=300s`, `MAX_RETRIES=3`

- **Acquire lease**: claim the oldest eligible job where `status='queued'` OR (`status='running'` AND `lock_expires_at < now()`), and set:
  - `status='running'`, `locked_by=<worker_id>`, `locked_at=now()`, `lock_expires_at=now()+LEASE_TTL`
  - Also set `works.ingestion_state = 'running'` at this moment (job claim time, not Upsert stage entry)
- **Renew lease**: while running, extend `lock_expires_at` every \(LEASE_TTL/3\).
- **Expiry**: if a worker dies, another worker may reclaim after expiry; all stages must be idempotent.
- **Retries**: on failure, increment `retry_count`; if `retry_count < MAX_RETRIES`, set `status='queued'` with backoff and set `works.ingestion_state = 'failed'` (stays `failed` until a retry run claims the job and sets it back to `running`); if `retry_count >= MAX_RETRIES`, set `status='failed'` and `works.ingestion_state = 'failed'` (terminal).

**Reference implementation shape (Postgres):**
- Eligibility predicate: `status='queued' OR (status='running' AND lock_expires_at < now())`
- Claim pattern: `SELECT id FROM ingestion_jobs WHERE (<eligibility>) ORDER BY created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED;`
  then `UPDATE ingestion_jobs SET status='running', locked_by=?, locked_at=now(), lock_expires_at=now()+LEASE_TTL WHERE id=? RETURNING *;`
- On success: set `status='succeeded'` and clear lease fields (`locked_by=NULL`, `locked_at=NULL`, `lock_expires_at=NULL`).
- Expired-claim behavior: reclaiming an expired `running` job does **not** increment `retry_count` by itself; only explicit stage failure increments retries.
- Backoff (MVP): exponential seconds `min(60, 2^retry_count)` + small jitter.
- **Recommended index for job polling performance:** `CREATE INDEX ON ingestion_jobs (status, created_at);` — required for the `FOR UPDATE SKIP LOCKED` claim query to avoid sequential scans.

### Worker retry restart semantics
A retry (whether automatic or user-triggered) **always restarts from the Fetch stage**, not from the failed stage. This keeps the retry logic simple and all stage idempotency rules self-consistent: Fetch skips if a good artifact exists, Embed skips already-embedded passages, and Upsert hard-replaces passages via cascade delete. There is no stage-level resume for MVP.

### Worker stages (idempotent)
- **Fetch**
  - Download raw content (text/HTML) and store in `source_artifacts` with provenance metadata (URL, status, hash, parser version)
  - **Idempotency on retry:** if a `source_artifacts` row already exists for this `source_id` with a successful `http_status` (2xx), skip the network call and reuse the existing artifact. Only re-fetch if no successful artifact exists.
- **Normalize**
  - Remove boilerplate (e.g., Gutenberg headers/footers)
  - Normalize whitespace; preserve headings when detectable
- **Chunk**
  - Passage-level segmentation (paragraph-aware)
  - Deterministic chunking given `raw_text` + `chunker_version`
  - Target chunk size defined by character count (MVP): ~900–1,800 characters
    - Merge tiny paragraphs; split very large ones
  - Produce stable `passage_index` and `citation_string`
  - **Deterministic chunking contract:** given identical `content_sha256` and `chunker_version`, the pipeline MUST produce identical `(passage_index, cleaned_text, citation_string)` for all passages.
  - `citation_string` format (MVP): `"{author} — {title}, {section_label or '§'}, ¶{passage_index}"`
  - **MVP chunking algorithm (pinned enough to implement):**
    - Paragraph detection: normalize newlines to `\n`, then split on blank lines (`\n\n+`).
    - Paragraph cleaning (pre-chunk): trim, collapse internal whitespace runs to single spaces.
    - Merge: accumulate paragraphs until adding the next paragraph would exceed ~1,800 chars; if current chunk < ~900 chars, keep merging even if it crosses a soft boundary (until it would exceed 1,800).
    - Split: if a single paragraph > 1,800 chars, split at the nearest sentence boundary to 1,200–1,800 chars (regex on `.?!` followed by space). If none found, hard-split at 1,800.
    - `section_label`: best-effort heading detection; if not stable/available, use `NULL` and render `'§'` in citations (do not invent).
      - **Heading detection heuristics (MVP, in priority order):**
        1. **Short all-caps line**: trimmed line is 3–60 chars, all uppercase letters/spaces/punctuation, preceded by a blank line. Example: `BOOK I`, `CHAPTER THE FIRST`.
        2. **"Chapter/Book/Part N" pattern**: case-insensitive match of `^(Chapter|Book|Part|Section|Canto|Act|Scene)\s+[\dIVXLCivxlc]+` at the start of a line, optionally followed by ` — ` or `: ` and a subtitle.
        3. **Short line after blank line**: trimmed line ≤ 60 chars, preceded and followed by blank lines, does not end with a period or comma (avoids treating short paragraphs as headings).
        - Apply heuristics in order; use the first match. If a line matches, it is consumed as the `section_label` for all subsequent passages until the next heading. Do not emit it as its own passage chunk.
        - If no heuristic fires for a work, all passages for that work have `section_label = NULL`.
- **Embed**
  - Compute embeddings locally via sentence-transformers
  - Batch for throughput
  - **Idempotency on retry:** use `INSERT INTO passage_embeddings ... ON CONFLICT (passage_id, embedding_model) DO NOTHING` — passages already embedded are skipped; only missing embeddings are computed and inserted.
- **Upsert**
  - Insert/update work + passages + embeddings
  - Mark work ingestion complete
  - **Re-ingestion semantics (idempotent):** On re-run of the same work (e.g., after a failed job is retried or a future `force=true` re-ingest):
    - `DELETE FROM passages WHERE work_id = ?` — cascade removes all associated `passage_embeddings` rows automatically.
    - Re-insert passages with fresh `passage_index` values from the current chunker run.
    - This hard-replace approach keeps the passage set consistent with the current artifact + chunker version. Any stale `passage_id`s held by a client become invalid after re-ingest (acceptable for MVP single-user scope).
  - **`works.ingestion_state` ownership:** Two writers, each with a defined scope:
    - **Worker (job claim):** sets `running` when the job is first acquired (see leasing section above)
    - **Worker (Upsert stage success):** sets `complete`; sets `works.ingested_at = now()`
    - **Worker (any stage failure):** sets `failed`
    - **API layer:** sets `queued` in two cases only: (a) new job created for a previously-unseen work; (b) new job created for a terminal-failed work (user-triggered retry). Never writes `running`, `complete`, or `failed`.

---

## Retrieval (Search)
1. Embed query locally
2. Vector similarity search in Postgres/pgvector (top-k)
3. Return passages with:
   - similarity score
   - work metadata
   - citation string
   - snippet (server-generated from `cleaned_text`): first 300 characters of `cleaned_text`, trimmed to the nearest word boundary; no ellipsis logic needed for MVP
   - optional query-term highlight via naive string match (not true lexical relevance)

### Embeddings + vector search (MVP pinned)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (384 dims)
- Similarity: cosine similarity (higher is better)
- pgvector index: HNSW on `passage_embeddings.embedding`, scoped to the single pinned model:
  ```sql
  CREATE INDEX ON passage_embeddings USING hnsw (embedding vector_cosine_ops)
    WHERE embedding_model = 'sentence-transformers/all-MiniLM-L6-v2';
  ```
  - Parameters: `m=16`, `ef_construction=64` (pgvector defaults; adequate for tens of thousands of 384-dim vectors)
  - Query-time `ef_search`: use pgvector default (40) for MVP
  - Partial index is required: a single HNSW index over mixed-model vectors would be incorrect (different vector spaces)

Future (post-MVP): hybrid retrieval (FTS + vector), reranking.

---

## RAG (Ask)

### Shared retrieval
Ask uses the same retrieval as Search to produce a **context pack**: top-k passages + citations.

### Answer modes (Hybrid)
- **Strict (default)**: “evidence-first”
  - Server requires a structured answer contract and validates grounding:
    - LLM produces a structured mapping: claims → quotes → `passage_id`s
    - Server validates each quote is a substring of the referenced `passages.cleaned_text` using normalized matching:
      - Unicode NFC, collapse whitespace runs to single spaces
      - normalize curly quotes to straight quotes
      - normalize dashes (em/en dashes → `-`)
      - strip simple footnote markers like `[\d+]` and `(\d+)` during validation only
      - case-fold (lowercase) for matching
    - If validation fails: one auto-repair attempt (regenerate with stricter prompt); otherwise return “Insufficient evidence”
  - Render output as quotations + citations.
- **Fluent (toggle)**: “explain”
  - LLM prompt requests natural prose with inline citation markers (e.g., `[1]`, `[2]`). No structured JSON contract.
  - Passages are numbered 1..k in the context pack prompt; the LLM is instructed to cite them using those numbers. The server maps `[N]` → `passage_id` of the Nth entry in `retrieved_passages`.
  - Server extracts `cited_passage_ids` by parsing `[N]` markers from the returned markdown. No grounding validation is performed in fluent mode.
  - The response includes `retrieved_passages` (full context pack) and `cited_passage_ids` (best-effort extracted from markers). If parsing fails, `cited_passage_ids` may be empty — this is acceptable for MVP.

### Transparency UX (required)
- Answer with inline citations
- Evidence panel listing all retrieved passages used in generation
- Disclose “How this answer was made”: `embedding_model`, `llm_model`, `k`, timestamp, and active filters

---

## API Surface (MVP)

### Corpus / ingestion
- `POST /api/ingest`
  - body: `{ source_type: "gutenberg"|"wikisource", locator: string }`
  - returns: `{ job_id: string|null, work_id: string }`
  - status codes:
    - `202` job created or active job reused (work is being or about to be ingested)
    - `200` no-op: work already `complete` and no new job was created (`job_id` will be `null`)
    - `400` invalid locator/source
  - error shape: `{ error: { code: string, message: string, details?: any } }`
  - **Idempotency:** if canonical (`source_type`, `locator`) exists, MUST return the existing `work_id`. It MUST NOT create a duplicate work. It may reuse an active job or enqueue a new one (explicitly documented in implementation).
- `GET /api/jobs/{job_id}`
  - returns status/progress/error
  - status codes: `200`, `404`
- `GET /api/works`
  - list works; query params: `?source_type=gutenberg|wikisource&author=<string>&title=<string>` (all optional; ANDed)
  - `author` and `title` filters use case-insensitive substring match (SQL `ILIKE '%value%'`); `source_type` is exact match
  - **No pagination for MVP**: returns all matching works in a single response (acceptable at ≤500 works; add pagination post-MVP if needed)
  - Response: `{ works: [{ work_id, title, author, language, source_type, ingestion_state, ingested_at, created_at }] }`
- `GET /api/works/{work_id}`
  - returns work metadata + paginated passages
  - query: `?cursor=<opaque>&limit=<int>`
  - status codes: `200`, `404`

### Search
- `POST /api/search`
  - body: `{ query: string, k: number, filters?: { source_type?: string[], author?: string[], work_ids?: string[], language?: string[] } }`
  - returns:
    - `results: [{ passage_id, work_id, citation_string, cleaned_text_snippet, score }]`
    - `meta: { k, embedding_model }`
  - status codes: `200`, `400`
  - `score` semantics: cosine similarity in \([-1, 1]\); higher is better.

### Ask
- `POST /api/ask`
  - body: `{ query: string, k: number, mode: "strict"|"fluent", filters?: { source_type?: string[], author?: string[], work_ids?: string[], language?: string[] } }`
  - filters are identical in shape and semantics to `POST /api/search` filters
  - `k` for Ask: defaults to **5**, min 1, max **20** (tighter than Search to fit retrieved passages in the local LLM's context window; 400 on violation)
  - returns:
    - `answer_markdown`
    - `retrieved_passages`: the full top-k context pack (id, work_id, citation_string, cleaned_text, score)
    - `cited_passage_ids`: subset actually cited in the rendered answer
    - `meta: { k, mode, embedding_model, llm_model }`
  - status codes: `200`, `400`

**Strict-mode structured contract (internal, deterministic validation target):**
- LLM must produce JSON matching:
  - `{ "claims": [ { "claim": string, "supports": [ { "passage_id": string, "quote": string } ] } ] }`
- Server renders `answer_markdown` from this JSON (so the markdown is derived, not free-form).
- `meta.strict_validation` is always present on strict-mode responses:
  - Success: `{ passed: true, attempts: 1 }` (or `2` if the auto-repair attempt succeeded)
  - Failure: `{ passed: false, attempts: 2 }` — accompanied by a standardized “Insufficient evidence” `answer_markdown` and `cited_passage_ids=[]`
- Fluent-mode responses omit `meta.strict_validation`.

---

## API Contracts (minimum precision)

### `GET /api/jobs/{job_id}` response shape
- `{ job_id, status, progress: { stage: "fetch"|"normalize"|"chunk"|"embed"|"upsert", fetched?: number, chunked?: number, embedded?: number, upserted?: number, total_passages?: number }, error?: string, retry_count, created_at, updated_at }`

### `GET /api/works/{work_id}` pagination
- Stable order: `passage_index ASC`
- Query: `?cursor=<opaque>&limit=<int>` — `limit` defaults to 50, min 1, max 200 (400 on violation)
- Response: `{ work: {...}, passages: [{ passage_id, passage_index, section_label, cleaned_text, citation_string }], next_cursor?: string }`
- `next_cursor` is absent (not null) when there are no more pages

### Filter semantics + validation defaults
- Filters are ANDed across fields; arrays within a field are ORed (e.g., `source_type in [...]`).
- `GET /api/works` accepts scalar string values for `author` and `title` query params (ILIKE match). `POST /api/search` and `POST /api/ask` accept `author?: string[]` in the JSON body (each element ORed with ILIKE). Single-element arrays and scalar strings are semantically equivalent.
- `k` for Search: defaults to 10, min 1, max 50 (400 on violation).
- `k` for Ask: defaults to 5, min 1, max 20 (400 on violation) — tighter to fit context into local LLM window.

### Ingest job dedupe + re-ingest trigger (MVP)
- `POST /api/ingest`:
  - If work exists and there is an active job (`queued` or `running`) for that work, return that `job_id` (no new job). HTTP `202`.
  - If work exists and `ingestion_state = 'complete'`, return `{ work_id, job_id: null }` (no-op). HTTP `200`. No new job unless `force=true` (post-MVP).
  - If work exists and `ingestion_state = 'failed'` **and** the associated job is terminal (`status='failed'`, `retry_count >= MAX_RETRIES`): create a new job with `retry_count=0`, set `works.ingestion_state = 'queued'`, return new `job_id`. HTTP `202`. This is the user-triggered retry path for terminal failures.
  - If work exists and `ingestion_state = 'failed'` **and** the associated job is non-terminal (already re-queued for automatic retry, `status='queued'`): return that existing `job_id`. HTTP `202`.

---

## UI Screens (MVP)

### Corpus Builder
- Input: Gutenberg ID/URL, Wikisource URL
- Job list: running/completed/failed + retry
- Library: works list; link to Work Detail

### Search
- Search bar + filters
- Passage result cards: expand, citation copy, jump to Work Detail

### Ask (RAG)
- Question box
- Strict/Fluent toggle
- Answer panel with inline citations
- Evidence panel showing retrieved passages used

### Work Detail
- Work metadata
- Passage viewer (pagination)

---

## Risks & Mitigations
- **Licensing**: restrict MVP ingestion to redistributable texts; store provenance + license notes.
- **Parsing variability (Wikisource)**: keep MVP scope to URL-based ingestion with best-effort cleaning; iterate on heuristics.
- **Performance on M1 CPU**: choose CPU-friendly embedding model; batch embeddings; keep top-k small by default.

