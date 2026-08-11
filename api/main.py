import os
import json
import uuid

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Any

from sse_queue import push_event, event_stream  # noqa: F401  (push_event lo usa el worker)

# ──────────────────────────────────────────────
app = FastAPI(title="WebScrappingUNAB API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


# ── Modelos ────────────────────────────────────
class SearchPayload(BaseModel):
    query: str = Field(..., min_length=1, description="Tema a buscar")
    sources: List[str] = Field(
        default=["stackoverflow"],
        description="Fuentes a consultar",
        min_length=1,
    )
    max_results: int = Field(default=30, ge=1, le=200)
    include_graph: bool = True
    include_wordcloud: bool = True


# ── Endpoints ──────────────────────────────────
@app.get("/health")
def health():
    """Healthcheck básico."""
    return {"status": "ok"}


@app.post("/search")
def search(payload: SearchPayload) -> Dict[str, Any]:
    """
    Crea un job, guarda el payload en Redis y encola el job_id
    para que el worker lo procese via BRPOP.
    Devuelve job_id para que el frontend abra /events?job_id=...
    """
    job_id = str(uuid.uuid4())

    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    # Guardar payload
    r.set(f"job:{job_id}:payload", payload.model_dump_json(), ex=600)

    # Estado inicial
    r.set(f"job:{job_id}:status", "queued", ex=600)

    # Encolar para el worker (BRPOP en el otro extremo)
    r.rpush("jobs:queue", job_id)

    return {"job_id": job_id}


@app.get("/events")
def events(job_id: str):
    """
    SSE stream: el frontend se suscribe aquí y recibe eventos
    en tiempo real mientras el worker procesa el job.
    """
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id requerido")

    return StreamingResponse(
        event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # importante para nginx
        },
    )


@app.get("/job_result")
def job_result(job_id: str):
    """
    Endpoint de debug/fallback: devuelve el resultado final
    almacenado en Redis sin necesidad de SSE.
    """
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id requerido")

    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    raw = r.get(f"job:{job_id}:result")

    if not raw:
        return {"job_id": job_id, "ready": False}

    return {"job_id": job_id, "ready": True, "result": json.loads(raw)}