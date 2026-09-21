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
from db import JobLog, SearchProvider, SearchQuery, get_session, init_db

# ──────────────────────────────────────────────
app = FastAPI(title="WebScrappingUNAB API")


@app.on_event("startup")
def on_startup() -> None:
    init_db()

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

    # Historial en Postgres: se inserta antes de encolar el job en Redis para
    # que la fila exista cuando el worker la desencole y empiece a llamar a
    # emit() (que escribe en job_logs, con FK a esta tabla). Best-effort: si
    # Postgres falla, no debe tumbar la creación del job (Redis/SSE sigue
    # siendo la vía crítica para que la búsqueda funcione).
    try:
        with get_session() as session:
            session.add(SearchQuery(
                id=job_id,
                query=payload.query,
                sources=payload.sources,
                max_results=payload.max_results,
                status="queued",
            ))
    except Exception as e:
        print(f"[api] no se pudo registrar la búsqueda en la base de datos (job_id={job_id}): {e}")

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


@app.get("/providers")
def get_providers() -> List[Dict[str, Any]]:
    """
    Catálogo de fuentes de búsqueda (activas, pendientes o bloqueadas),
    sembrado por db/seed.py. Solo lectura.
    """
    with get_session() as session:
        providers = session.query(SearchProvider).order_by(SearchProvider.slug).all()
        return [
            {
                "slug": p.slug,
                "display_name": p.display_name,
                "status": p.status,
                "description": p.description,
                "rate_limit_info": p.rate_limit_info,
                "requires_auth": p.requires_auth,
            }
            for p in providers
        ]


@app.get("/search_history")
def get_search_history(limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """
    Historial de búsquedas (tabla search_queries), paginado y ordenado por
    fecha de creación descendente.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    with get_session() as session:
        total = session.query(SearchQuery).count()
        rows = (
            session.query(SearchQuery)
            .order_by(SearchQuery.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        items = [
            {
                "job_id": q.id,
                "query": q.query,
                "sources": q.sources,
                "max_results": q.max_results,
                "status": q.status,
                "summary": q.summary,
                "posts_count": q.posts_count,
                "error_message": q.error_message,
                "created_at": q.created_at,
                "completed_at": q.completed_at,
            }
            for q in rows
        ]

    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/search_history/{job_id}/logs")
def get_search_history_logs(job_id: str) -> Dict[str, Any]:
    """
    Log estructurado (tabla job_logs) de una búsqueda puntual, en orden
    cronológico.
    """
    with get_session() as session:
        query_row = session.get(SearchQuery, job_id)
        if not query_row:
            raise HTTPException(status_code=404, detail="job_id no encontrado")

        logs = (
            session.query(JobLog)
            .filter(JobLog.job_id == job_id)
            .order_by(JobLog.created_at.asc())
            .all()
        )
        return {
            "job_id": job_id,
            "logs": [
                {
                    "stage": log.stage,
                    "level": log.level,
                    "message": log.message,
                    "data": log.data,
                    "created_at": log.created_at,
                }
                for log in logs
            ],
        }