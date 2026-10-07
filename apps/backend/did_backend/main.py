from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="DID API")


@app.get("/api/health")
def health():
    return {"status": "ok"}


frontend = Path(__file__).resolve().parents[3] / "apps/frontend/dist"
if frontend.is_dir():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")


def run():
    import uvicorn
    uvicorn.run("did_backend.main:app", host="127.0.0.1", port=8000)
