# Dev Log

Lightweight, append-only log of notable work on this repo.

## For agents (read this first)

**Owner intent:** This file is **not** just housekeeping — it should stay **useful for technical interviews** (and resume talking points). When you finish meaningful work, **append a dated entry** (or extend the latest day if it's the same session) so the human can later answer "what did you build?", "why that design?", and "what went wrong?"

**Write entries so they help interview prep:**

- **Product / problem framing** in plain English (what the system does for users).
- **Architecture & tradeoffs** (stack choices, why Postgres + pgvector, job queue, idempotency, etc.) — short bullets, not essays.
- **Honest scope:** what shipped vs what's still planned (credibility beats hype).
- **War stories:** bugs, migration failures, test/transaction gotchas, **how you fixed them** — interviewers love concrete debugging.
- **Numbers / scale hints** when relevant (model name, dims, rough limits like `k`, lease TTL).
- **Follow-ups** as checkboxes under **Next** when useful.

**Do not** replace or rewrite past entries (append-only). **Do not** put secrets (tokens, production URLs, private data) in this file.

## Format (copy/paste)

```md
## YYYY-MM-DD

**Focus:** <1 sentence — what problem or feature this session attacked>

**What it does (user-facing):**
- <plain English: what can a user now do that they couldn't before?>

**Architecture & tradeoffs:**
- <stack choice + why: e.g. "pgvector over Pinecone — zero cost, single-DB, good enough at MVP scale">
- <design decision + the alternative you rejected and why>

**Changes shipped:**
- <file/module + what it does — enough to reconstruct intent without reading the code>

**War stories (bugs + fixes):**
- <what broke, why it broke, how you diagnosed it, what the fix was — interview gold>

**Honest scope:**
- Done: <what actually works end-to-end>
- Not done: <what's still stubbed, mocked, or missing>

**Numbers:**
- <model name, dims, k defaults, TTL, batch size, row counts — anything concrete>

**Next:**
- [ ] <next step>
```

---

## 2026-05-02

**Focus:** Initialize the dev log.

**Changes shipped:**
- Added `docs/dev-log.md` with entry template and agent instructions.

**Next:**
- [x] Add an entry whenever meaningful work ships.

---

## 2026-05-04

**Focus:** Defined the product, chose the stack, scaffolded the full repo, and got local dev (DB, migrations, tests, health endpoint) working end-to-end.

**What it does (user-facing):**
- Users will be able to paste a Gutenberg ID or Wikisource URL into a Corpus Builder, trigger a background ingestion job, then search passages semantically or ask questions with cited answers — all running locally with no hosted API cost.

**Architecture & tradeoffs:**
- **Postgres + pgvector** over a managed vector DB (Pinecone, Weaviate): single service, zero extra cost, full SQL for joins and filtering, good enough at MVP scale (~500 works, tens of thousands of passages).
- **DB-backed job queue** (leasing + `FOR UPDATE SKIP LOCKED`) over Celery/Redis: one fewer infra dependency; Postgres is already in the stack; idempotent stages mean retries are safe without a separate broker.
- **Local Ollama** over OpenAI API: zero per-query cost, works offline, runs well on Apple Silicon unified memory.
- **Strict-mode RAG** (structured JSON + server-side quote validation) as default, fluent as opt-in: grounding is verifiable without trusting the LLM to self-police — hallucinated citations are the core failure mode in RAG.
- **Monorepo** (`apps/api` + `apps/web`): colocated types and shared `.env` patterns; small team, no need for separate repos.

**Changes shipped:**
- Monorepo layout: `apps/api` (FastAPI), `apps/web` (Next.js), root `README.md`, `.gitignore`.
- `app/db/models.py`: `sources`, `source_artifacts`, `works`, `passages`, `passage_embeddings`, `ingestion_jobs` — CHECK constraint (`raw_text XOR raw_html`) + trigger (`passage_embeddings.work_id` must match `passages.work_id`).
- Alembic initial migration + `CREATE EXTENSION IF NOT EXISTS vector`.
- `/api/health` endpoint + pytest `conftest.py` with `TEST_DATABASE_URL` guard (refuses to run against non-`_test` DB).
- Job leasing unit tests.

**War stories (bugs + fixes):**
- **`pip install -e` failed silently** — had to run from `apps/api`, not repo root (root has no `pyproject.toml`).
- **Setuptools picked up `alembic/` as a second top-level package** alongside `app/` — broke imports; fixed with explicit `[tool.setuptools.packages.find]` in `pyproject.toml`.
- **Alembic `DuplicateObject: type source_type already exists`** — migration created the ENUM in raw SQL, then SQLAlchemy tried to create an empty duplicate ENUM on `CREATE TABLE`. Fix: `postgresql.ENUM(..., create_type=False)` + idempotent `DO $$ … duplicate_object` guard block in migration.
- **`InvalidRequestError: A transaction is already begun`** in leasing tests — SQLAlchemy autobegin starts a transaction at session creation; calling `begin()` again errors. Fix: use `begin_nested()` (savepoint) instead.

**Honest scope:**
- Done: repo scaffold, DB schema + migrations, health endpoint, job leasing, all tests passing.
- Not done: ingestion fetchers, chunker, embedder, worker pipeline, all public REST routes, UI wired to API.

**Numbers:**
- Embedding model (planned): `sentence-transformers/all-MiniLM-L6-v2`, 384 dims
- Job leasing: `LEASE_TTL=300s`, `MAX_RETRIES=3`
- Target scale: ~500 works, tens of thousands of passages

**Next:**
- [x] Tasks 7–11: ingestion pipeline → worker orchestration → ingest/jobs/works HTTP API.
- [ ] Add README "Interview demo script" (docker up → migrate → ingest sample Gutenberg ID → search/ask).

---

## 2026-05-05

**Focus:** Shipped the full ingest-to-search backend: fetchers, chunker, embedder, worker orchestration, and the ingest/jobs/works HTTP API.

**What it does (user-facing):**
- A user can now POST a Gutenberg ID or Wikisource URL, watch ingestion progress via job polling, and query the resulting passages. The work appears in the library and is fully searchable once the job completes.

**Architecture & tradeoffs:**
- **Artifact reuse on retry**: Fetch stage checks for an existing successful artifact before hitting the network — idempotency without re-downloading on every retry.
- **Normalize as pure in-memory transform**: `normalize_text()` runs inside `chunk_work`, not as a separate DB stage — no unnecessary write, keeps the stage boundary clean.
- **Hard-replace on re-ingest**: `DELETE FROM passages WHERE work_id=?` cascades to embeddings via FK; simpler than upsert-by-index and guarantees a clean slate for each ingest run.
- **Partial HNSW index scoped to the pinned model**: prevents mixing vector spaces if a second embedding model is ever added; required by pgvector — one HNSW index can't span multiple vector spaces.
- **Spec/plan docs gitignored**: keeps the remote repo clean; local `docs/` is the source of truth.

**Changes shipped:**
- `app/ingest/canonicalize.py`: Gutenberg numeric ID extraction + Wikisource URL normalization (enforce `https://en.wikisource.org/wiki/<Title>`, strip query/fragment).
- `app/ingest/fetch_gutenberg.py` / `fetch_wikisource.py`: HTTP fetch with artifact idempotency; store `raw_text` (Gutenberg) or `raw_html` (Wikisource) — never both.
- `app/ingest/normalize.py` + `chunk.py`: header/footer stripping; deterministic paragraph chunking (900–1800 chars, sentence-boundary splits, heading heuristics); stable `citation_string`.
- `app/ingest/embed.py`: MiniLM batch embeddings; `ON CONFLICT (passage_id, embedding_model) DO NOTHING` idempotency; Alembic migration for partial HNSW cosine index.
- `app/worker/worker.py`: `run_ingest_job` orchestrates fetch → normalize → chunk → hard-replace → embed; updates `progress.stage` and `works.ingestion_state` atomically at job claim and on success/failure.
- `POST /api/ingest`, `GET /api/jobs/{job_id}`, `GET /api/works`, `GET /api/works/{work_id}`: full dedupe logic (active job reuse → 202, complete no-op → 200, terminal-failed retry → new job 202).
- `app/db/deps.py`, `app/api/errors.py`: spec-shaped error JSON; DB session override pattern for test isolation; per-test `TRUNCATE` to prevent state leak between tests.

**Honest scope:**
- Done: full ingest pipeline end-to-end, worker with retries and leasing, ingest/jobs/works API with all dedupe branches tested, `pytest` fully green.
- Not done: Search API, Ask API, UI wired to real data.

**Numbers:**
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`, 384 dims
- Chunk target: 900–1800 chars; hard split at 1800 if no sentence boundary found
- HNSW: `m=16`, `ef_construction=64`, `ef_search=40` (pgvector defaults)

**Next:**
- [x] Task 12 (Search): `POST /api/search` — pgvector cosine query, `k` bounds, filters, snippet.
- [x] Task 13 (Ask): `POST /api/ask` + Ollama client + strict/fluent tests.
- [x] Tasks 14–17: Next.js UI wired to API (corpus, search, ask, work detail).

---

## 2026-05-05 — Search API (Task 12)

**Focus:** Ship `POST /api/search` for passage-level semantic retrieval over pgvector.

**What it does (user-facing):**
- Users type a query and get back the most semantically similar passages from their corpus, ranked by cosine similarity, with scores, citations, and a text snippet — filterable by source type, author, language, or specific work IDs.

**Architecture & tradeoffs:**
- **Cosine similarity via pgvector** (`1 - (embedding <=> query_vec)`): native operator, uses the HNSW index, consistent with ingest embedding metric.
- **Dependency-injected encoder** (`Depends(get_encode_query_vector)`): lets tests swap in fixed orthogonal unit vectors without monkeypatching — fast, deterministic tests with zero model loading overhead on the hot path.

**Changes shipped:**
- `app/api/search.py`: query validation (`query` non-empty after strip, `k` 1–50 default 10); pgvector cosine query scoped to pinned model; AND-across-fields / OR-within-arrays filter logic; `cleaned_text_snippet` = first 300 chars trimmed back to nearest word boundary.
- `tests/test_search_api.py`: orthogonal unit-vector override for fast, deterministic results.
- `app/main.py`: search router registered.

**Honest scope:**
- Done: search with filters, scores, snippets, citations.
- Not done: hybrid FTS + vector reranking (post-MVP).

**Numbers:**
- `k` default 10, min 1, max 50
- Snippet: first 300 chars trimmed to nearest word boundary

**Next:**
- [x] Ask API (`POST /api/ask`) reusing retrieval + Ollama stubs.

---

## 2026-05-05 — Ask API (Task 13)

**Focus:** `POST /api/ask` with strict JSON quote-grounding and fluent `[N]` citation mode; Ollama behind injectable client.

**What it does (user-facing):**
- Users ask a question; the server retrieves the top-k passages, sends them to a local LLM, and returns a cited answer. Strict mode validates that every quote is a real substring of the source passage. Fluent mode returns natural prose with `[N]` citation markers.

**Architecture & tradeoffs:**
- **Strict-mode server-side validation**: LLM must emit structured JSON (`{ claims: [{ claim, supports: [{ passage_id, quote }] }] }`); server validates each quote against `cleaned_text` after normalization. One auto-repair attempt before returning "Insufficient evidence." Chose server-side over trusting the LLM — hallucinated citations are the core failure mode in RAG.
- **Fluent mode as a separate prompt path**: free-form prose with numbered `[N]` markers; server extracts cited IDs by regex against the context pack order. No grounding validation — simplicity over strictness for the casual mode.
- **Ollama client injectable** via `Depends()`: same pattern as the encoder — swap in a fake for tests, no live LLM required in CI.

**Changes shipped:**
- `app/llm/grounding.py`: quote normalization (Unicode NFC, whitespace collapse, curly→straight quotes, em/en-dash→hyphen, footnote marker strip, case-fold); strict JSON parse + validate; fluent `[N]` regex extractor.
- `app/llm/prompts.py`: strict, repair, and fluent prompt templates.
- `app/llm/ollama_client.py`: `POST /api/generate`, configurable timeouts, `OLLAMA_MODEL` + `OLLAMA_BASE_URL` env vars.
- `app/api/ask.py`: `k` default 5 max 20; repair-once control flow; `meta.strict_validation` on strict responses, omitted on fluent; `meta.timestamp` + echoed filters.
- `tests/test_ask_strict_validation.py`: fake Ollama + encoder override — no live LLM in CI.
- `app/settings.py` / `.env.example`: Ollama defaults documented.

**War stories (bugs + fixes):**
- **Strict validation false negatives**: LLM would slightly rephrase quotes (curly quotes, em-dash vs hyphen). Fixed by normalizing both the LLM output and the passage text before substring match — not just one side.

**Honest scope:**
- Done: strict + fluent modes, quote validation, repair loop, `meta.strict_validation`, all tested with stubs.
- Not done: streaming responses, live Ollama integration test.

**Numbers:**
- Ask `k` default 5, min 1, max 20 (tighter than search — local LLM context window budget)
- Strict mode: max 2 LLM attempts before "Insufficient evidence"

**Next:**
- [x] Tasks 14–17: Next.js UI wired to API.

---

## 2026-05-05 — UI (Tasks 14–17)

**Focus:** Wire the Next.js App Router to the FastAPI backend — all four pages functional with real data.

**What it does (user-facing):**
- **Corpus Builder**: paste a Gutenberg ID, watch ingestion progress live, library fills in as jobs complete.
- **Search**: type a query, get ranked passage results with copyable citations and links to work detail.
- **Ask**: toggle strict/fluent, see the grounded answer in markdown plus an evidence panel showing every retrieved passage with cited rows highlighted.
- **Work detail**: browse all passages in a work with cursor-based infinite scroll.

**Architecture & tradeoffs:**
- **TanStack Query** for server state: handles job polling, cache invalidation on ingest, and stale-while-revalidate — no manual loading state management in components.
- **Typed `src/lib/api.ts`**: single source of truth for request/response shapes; keeps component code thin and catches API contract drift at compile time.
- **`NEXT_PUBLIC_API_BASE_URL` build-time constant**: avoids runtime env detection that caused mysterious `NetworkError` failures when the value was resolved differently server-side vs client-side.

**Changes shipped:**
- `src/lib/api.ts`: typed API client for all endpoints.
- `src/lib/queryClient.ts`: TanStack Query setup.
- Corpus page: ingest form, job polling with progress bar + status pill, works list.
- Search page: debounced input (~400ms), k + filter controls, result cards with citation copy.
- Ask page: strict/fluent toggle, markdown answer render (`react-markdown`), evidence panel with cited-row highlight.
- Work detail: cursor-based "load more" pagination.

**Honest scope:**
- Done: all four pages wired to real API data, TanStack Query, typed client.
- Not done: error boundary polish, empty states, mobile layout.

**Next:**
- [x] E2E hardening, delete workflow, metadata extraction, styling fixes.

---

## 2026-05-06

**Focus:** E2E hardening — corpus deletion from UI, work metadata extraction, fluent citation reliability, CORS, and a DB session lifecycle bug that was silently dropping all writes.

**What it does (user-facing):**
- Users can delete works from the Library and Work Detail page (with confirm dialog).
- Work titles and authors now populate correctly from Gutenberg headers and Wikisource HTML during ingestion instead of showing blank.

**Architecture & tradeoffs:**
- **Delete order is explicit, not cascade-only**: `passage_embeddings.work_id` has a RESTRICT FK separate from the passage CASCADE — must delete embeddings first, then passages, then work + source. Cascade alone wasn't sufficient because `work_id` is a denormalized FK that doesn't cascade.
- **Fluent one-time retry**: if the first generation returns zero `[N]` markers, retry once with a stricter prompt — small corrective loop rather than full strict-mode overhead for a UX that should feel casual.

**Changes shipped:**
- `DELETE /api/works/{work_id}`: deletes embeddings → passages → work + source in correct FK order; test seeds an embedding row to guard the deletion sequence against regressions.
- Corpus + Work Detail UI: Delete button with confirm dialog.
- `app/ingest/`: best-effort `Title`/`Author`/`Language` extraction from Gutenberg header lines; Wikisource title from `<title>` tag or URL slug. Populates `works.*` during ingestion.
- CORS middleware: allowed `localhost:3000` and LAN origins for local dev.
- Fluent prompt: explicit `[N]` citation instruction + one citation-retry on zero-citation response.
- `get_db_session()`: now commits on success and rolls back on exception (was missing commit).
- `postcss.config.cjs`: renamed from `.mjs` so PostCSS loader picks it up correctly.
- Root `README.md`: recruiter-friendly overview + Quickstart demo section; pushed to GitHub.

**War stories (bugs + fixes):**
- **Deletes "worked" but the work still showed up in the library.** Spent time checking the delete logic — it was correct. Root cause: the request-scoped SQLAlchemy session never called `commit()`; changes lived in the transaction and were silently rolled back at session close. Fix: `get_db_session()` dependency now commits on success and rolls back on exception. This was a silent bug affecting every write endpoint, not just delete.
- **UI completely unstyled after adding PostCSS.** Tailwind classes rendered as plain text. Root cause: `postcss.config.mjs` (ES module) wasn't picked up by the PostCSS loader which expects CJS. Fix: rename to `postcss.config.cjs`. Rule of thumb: if Tailwind styles suddenly vanish, check PostCSS config format before anything else.

**Honest scope:**
- Done: delete flow end-to-end, metadata extraction, fluent citation retry, CORS, session lifecycle fix, Tailwind working, README on GitHub.
- Not done: Task 19 README smoke-run + demo script.

**Numbers:**
- Fluent mode: max 2 LLM attempts (1 initial + 1 citation-retry)

**Next:**
- [ ] Task 19: README smoke-run + demo script (docker up → migrate → run API/worker/web → ingest Gutenberg 1342 → search → ask → delete/re-ingest).

---

## 2026-05-06 — Rename + metadata + passage cleanup

**Focus:** Rename project from `philosophia-engine` to `commonplace`; fix Gutenberg metadata always showing "Untitled"; strip italic markup from passage text.

**What it does (user-facing):**
- Works now show correct title and author in the library for any Gutenberg book regardless of file format age.
- Passage text no longer has `_underscore_` markers cluttering the reading view.

**Architecture & tradeoffs:**
- **Gutendex API for metadata** over parsing raw text: old-format Gutenberg files (pre-2000s) have no `Title:`/`Author:` header lines — the text-parsing approach silently returned null for them. Gutendex (`gutendex.com/books/{id}`) is a free structured catalog API that works for every Gutenberg ID. Text-parse kept as a fallback.
- **Author name flip**: Gutendex returns `"Austen, Jane"` (catalog format) — worker flips to `"Jane Austen"` on ingest.

**Changes shipped:**
- `app/ingest/metadata.py`: `fetch_gutenberg_metadata_api()` calls Gutendex; falls back to text header parsing if API returns incomplete data.
- `app/worker/worker.py`: Gutenberg ingest now calls Gutendex first, merges with text-parse fallback.
- `app/ingest/normalize.py`: `strip_gutenberg_markup()` removes `_italics_` and `^{superscript}` conventions before chunking.
- Project renamed to `commonplace` everywhere: GitHub repo, local directory, DB names (`philosophia` → `commonplace`), Docker Compose project name pinned, all in-code references updated.

**War stories (bugs + fixes):**
- **Metadata returned null for all books tested (1342, 42671).** Both are old-format Gutenberg files where the raw text starts directly with `*** START OF THE PROJECT GUTENBERG EBOOK ***` — no `Title:`/`Author:` header exists in the file at all. Text parsing silently returned null. Fix: switched to Gutendex API as primary source.
- **Renaming the directory broke the venv.** Python venvs have absolute paths baked in — moving the folder made all venv executables point to a non-existent path. Fix: delete and recreate the venv (`rm -rf .venv && python3.11 -m venv .venv`).
- **Docker Compose created a new empty database** after the rename because the project name (derived from directory name) changed, generating a new volume. Fix: copied data from `philosophia-engine_postgres_data` to `commonplace_postgres_data` using an Alpine container, then pinned `name: commonplace` in `docker-compose.yml`.
- **Postgres rename blocked by active sessions.** `ALTER DATABASE philosophia RENAME TO commonplace` failed with "being accessed by other users." Fix: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'philosophia'` first.

**Honest scope:**
- Done: metadata works for any Gutenberg book, passage text is clean, project fully renamed.
- Not done: Task 19 smoke-run demo script.

**Next:**
- [ ] Task 19: README smoke-run + demo script.

---

## 2026-05-06 — RAG testing + model limitations

**Focus:** End-to-end testing of Ask (strict + fluent) with Pride and Prejudice; identified model limitations and good demo questions.

**What it does (user-facing):**
- Fluent mode works well — returns cited prose answers with `[N]` markers and evidence panel highlighting. Good for demos.
- Strict mode correctly returns "Insufficient evidence" rather than hallucinating when Mistral can't extract a verbatim quote.

**Architecture & tradeoffs:**
- **Two models, two jobs:** MiniLM (`all-MiniLM-L6-v2`) handles retrieval (query → vectors → top-k passages); Mistral (via Ollama) handles generation (passages → answer). Users sometimes conflate them — worth being clear in interviews.
- **Strict mode is a correctness gate, not a failure.** "Insufficient evidence" is the honest, safe response when the LLM can't ground a claim verbatim. Mistral 7B struggles reliably with JSON schema output — `llama3` or `mistral-nemo` would improve strict mode hit rate.

**War stories (bugs + fixes):**
- **Retrieval doesn't surface the famous "tolerable, but not handsome enough to tempt me" quote** for the query "What is Mr. Darcy's first impression of Elizabeth?" — the passage exists in the corpus but MiniLM doesn't rank it highly for that phrasing. Semantic search is query-sensitive; rephrasing or increasing k helps. Good interview talking point about retrieval limitations.
- **Strict mode returning "Insufficient evidence" on valid questions** — not a bug, a model limitation. Mistral 7B doesn't reliably follow strict JSON schemas with verbatim quote constraints. Architecture is correct; swap the model to improve.

**Honest scope:**
- Done: fluent mode working with citations and evidence panel; strict mode working as a grounding gate.
- Not done: strict mode reliable with Mistral 7B on all questions; streaming responses.

**Numbers:**
- Fluent mode: `[1]`, `[2]` markers parsed and mapped to `retrieved_passages[N-1]`
- Good demo questions: "How does Elizabeth feel about Wickham?" (fluent), theme/character questions that span multiple passages
- Avoid for demos: single-quote lookup questions like "What exactly did Darcy say at the ball?" — retrieval is semantic, not lexical

**Next:**
- [ ] Try `llama3` (`ollama pull llama3`, set `OLLAMA_MODEL=llama3`) to improve strict mode reliability.
- [ ] Task 19: README smoke-run + demo script.

---

## 2026-05-11 — Hybrid Search (BM25 + pgvector RRF)

**Focus:** Replace pure-vector search with hybrid retrieval to fix recall gaps for keyword queries (proper nouns, character names).

**What it does (user-facing):**
- Search now surfaces passages that match by keyword *or* semantics, not just one. "Wickham" now returns Wickham passages even if MiniLM didn't rank them highly by cosine similarity.

**Architecture & tradeoffs:**
- **GIN expression index** on `to_tsvector('english', cleaned_text)` — no new column; Postgres indexes the function expression and maintains it on insert. Applied via Alembic migration; existing passages indexed immediately.
- **Two-arm CTE**: vector arm (top-4× k by cosine distance) + FTS arm (top-4× k by `ts_rank`) run in a single SQL query. Merged via FULL OUTER JOIN with Reciprocal Rank Fusion: `1/(60+rank_v) + 1/(60+rank_f)`. Passages absent from one arm get penalty rank `4k+1`.
- **RRF over linear blend**: RRF's 60-constant is robust without tuning; linear blends require knowing that cosine [0,1] and ts_rank [0,1] are comparable, which they aren't without normalization.
- **Ask endpoint unchanged**: Ask uses `retrieve_passages_similarity` (pure vector). For generation, semantic context matters more than keyword recall.
- **`text("'english'")` for language param**: must emit a SQL literal (not a bind parameter) so Postgres can match the GIN index expression at query-plan time.

**Changes shipped:**
- `alembic/versions/20260511_000003_passages_fts_gin.py`: GIN index migration.
- `app/api/search.py`: `retrieve_passages_hybrid` — two-arm CTE with RRF merge; search endpoint wired to it; response uses `rrf_score` + `meta.retrieval: "hybrid"`.
- `tests/test_search_api.py`: renamed score assertions; new `test_search_hybrid_surfaces_fts_match` seeds an orthogonal passage with the target keyword and verifies it surfaces despite poor vector rank.
- `apps/web/src/lib/api.ts` + `search/page.tsx`: updated to `rrf_score`.

**Honest scope:**
- Done: hybrid search on the search endpoint, existing tests updated, FTS-specific test added, TypeScript types updated.
- Not done: Ask hybrid retrieval (deliberately excluded), query-time language detection (hardcoded 'english'), FTS weight tuning (A/B/C/D column weights).

**Numbers:**
- Over-fetch factor: 4× per arm (e.g. k=10 → 40 candidates per arm, merge to top 10)
- RRF constant: 60 (standard; no tuning needed)
- GIN index type: `gin(to_tsvector('english', cleaned_text))`
