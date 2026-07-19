from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Any
import json
import uuid
import os
import redis

from sse_queue import push_event, event_stream  # nuevos archivos (abajo)

app = FastAPI(title="WebScrappingUNAB API")

# CORS para frontend (Vite en 8080->80 en docker)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


class SearchPayload(BaseModel):
    query: str = Field(..., min_length=1, description="Tema/dolencia a buscar")
    sources: List[str] = Field(
        default=["reddit", "stackoverflow"],
        description="Fuentes a consultar (MVP soporta 2: reddit, stackoverflow)",
        min_length=1,
    )
    max_results: int = Field(default=30, ge=1, le=200)
    include_graph: bool = True
    include_wordcloud: bool = True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search")
def search(payload: SearchPayload) -> Dict[str, Any]:
    # Crea un job_id y publica un evento "enqueue" para el worker.
    job_id = str(uuid.uuid4())

    # Guarda payload como JSON en Redis
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    r.set(f"job:{job_id}:payload", payload.model_dump_json())

    # Estado inicial
    r.set(f"job:{job_id}:status", "queued")

    # Notificar al worker por un stream/list
    # Usamos LIST para MVP: worker hace BRPOP.
    r.rpush("jobs:queue", job_id)

    # Devuelve job_id para que el frontend abra el SSE
    return {"job_id": job_id}


@app.get("/events")
def events(job_id: str):
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id requerido")

    # Stream SSE: consume eventos que el worker empuja a Redis (per job)
    gen = event_stream(job_id)
    return StreamingResponse(gen, media_type="text/event-stream")


@app.get("/job_result")
def job_result(job_id: str):
    """Endpoint opcional para debug (no requerido para SSE)."""
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id requerido")

    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    key = f"job:{job_id}:result"
    raw = r.get(key)
    if not raw:
        return {"job_id": job_id, "ready": False}
    return {"job_id": job_id, "ready": True, "result": json.loads(raw)}