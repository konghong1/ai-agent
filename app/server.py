from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.agent import ask_agent


app = FastAPI(title="Local LangChain AI Agent", version="0.1.0")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        thread_id = request.thread_id or "local-debug"
        return ChatResponse(answer=ask_agent(request.message, thread_id=thread_id), thread_id=thread_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
