from __future__ import annotations

from fastapi import FastAPI

from app.api import router
from app.core.database import init_db


app = FastAPI(title="Configurable AI Agent Platform", version="0.2.0")
app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
