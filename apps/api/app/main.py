from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.ask import router as ask_router
from app.api.ingest import router as ingest_router
from app.api.jobs import router as jobs_router
from app.api.search import router as search_router
from app.api.works import router as works_router


app = FastAPI(title="philosophia-api")

# UI is a separate origin (Next dev server), so we must allow browser CORS.
app.add_middleware(
    CORSMiddleware,
    # Dev UI runs on Next.js (often localhost OR a LAN IP like 10.x.x.x).
    # Allow any http://<host>:3000 origin for local development.
    allow_origin_regex=r"^http://.+:3000$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(ingest_router)
app.include_router(jobs_router)
app.include_router(search_router)
app.include_router(ask_router)
app.include_router(works_router)

