from fastapi import FastAPI


app = FastAPI(title="philosophia-api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

