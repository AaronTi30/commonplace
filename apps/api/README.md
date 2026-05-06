# philosophia-api

FastAPI skeleton for the philosophia-engine API.

## Run (dev)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/philosophia'
alembic upgrade head
uvicorn app.main:app --reload
```

