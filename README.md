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

## Development (placeholders)

### Database (Postgres + pgvector)

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
uvicorn app.main:app --reload
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

