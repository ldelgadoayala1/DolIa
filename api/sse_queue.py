import os
import json
import redis
from typing import Generator

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def push_event(job_id: str, event: dict) -> None:
    """
    Empuja un evento SSE a una lista Redis asociada al job.
    Formato esperado por frontend:
      { "stage": "...", "progress": 0-100, "status": "...", "type": "...", "data": {...} }
    """
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    key = f"job:{job_id}:events"
    r.rpush(key, json.dumps(event))


def event_stream(job_id: str) -> Generator[str, None, None]:
    """
    Produce una respuesta SSE.
    Convención SSE:
      event: <stage opcional>
      data: <json> 
    """
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    events_key = f"job:{job_id}:events"

    # Si no hay eventos aún, esperamos con BRPOP sobre la lista.
    # Cuando el worker mande type="done", cortamos.
    while True:
        item = r.brpop(events_key, timeout=60)
        if not item:
            # timeout: enviamos keep-alive para que el browser siga abierto
            yield "event: keepalive\n" "data: {}\n\n"
            continue

        _, raw = item
        payload = json.loads(raw)

        # En SSE el formato típico es:
        # data: <string>\n\n
        # (siempre enviamos data como JSON string)
        yield "data: " + json.dumps(payload) + "\n\n"

        if payload.get("type") == "done" or payload.get("type") == "error":
            break