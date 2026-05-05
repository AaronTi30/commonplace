from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.ingest import router as ingest_router
from app.api.jobs import router as jobs_router
from app.api.works import router as works_router


app = FastAPI(title="philosophia-api")


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
app.include_router(works_router)

