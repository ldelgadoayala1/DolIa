import os
import json
import time
import redis
from typing import Generator

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STREAM_TIMEOUT = 240  # segundos máximo esperando eventos (scrape + 2 lotes de anotación + relaciones de grafo, todo vía LLM)


def push_event(job_id: str, event: dict) -> None:
    """Worker llama esto para empujar eventos SSE a Redis."""
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    key = f"job:{job_id}:events"
    r.rpush(key, json.dumps(event))
    # TTL de 10 minutos para no acumular basura en Redis
    r.expire(key, 600)


def event_stream(job_id: str) -> Generator[str, None, None]:
    """
    API llama esto para hacer streaming SSE al frontend.
    Lee eventos desde Redis LIST usando polling liviano.
    """
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    key = f"job:{job_id}:events"
    status_key = f"job:{job_id}:status"
    index = 0
    deadline = time.time() + STREAM_TIMEOUT

    # Evento inicial de conexión
    yield f"data: {json.dumps({'type': 'connected', 'job_id': job_id})}\n\n"

    while time.time() < deadline:
        # Leer todos los eventos nuevos desde el índice actual
        events = r.lrange(key, index, -1)

        for raw in events:
            index += 1
            try:
                event = json.loads(raw)
            except Exception:
                continue

            yield f"data: {json.dumps(event)}\n\n"

            # Si el evento es terminal, cerramos el stream
            if event.get("type") in ("done", "error"):
                return

        # Verificar si el job ya terminó aunque no haya más eventos
        status = r.get(status_key)
        if status in ("done", "error"):
            # Dar un último intento de vaciar la cola
            remaining = r.lrange(key, index, -1)
            for raw in remaining:
                try:
                    yield f"data: {json.dumps(json.loads(raw))}\n\n"
                except Exception:
                    pass
            return

        # Polling cada 300ms para no saturar Redis
        time.sleep(0.3)

    # Timeout alcanzado
    yield f"data: {json.dumps({'type': 'error', 'message': 'Stream timeout'})}\n\n"