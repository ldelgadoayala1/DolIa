import os
import json
import time
import redis
from typing import Generator

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
# Segundos máximos SIN recibir eventos antes de cortar el stream. Antes era
# un límite absoluto de 240s para todo el job, y un job con max_results=30
# tarda ~8 min: el frontend recibía "Stream timeout" con el worker todavía
# trabajando (HU-06). Ahora el plazo se reinicia con cada evento; el worker
# emite uno por lote de clasificación, así que solo se corta si el job queda
# realmente colgado. 600s = mismo TTL que las claves del job en Redis.
STREAM_IDLE_TIMEOUT = 600


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
    deadline = time.time() + STREAM_IDLE_TIMEOUT

    # Evento inicial de conexión
    yield f"data: {json.dumps({'type': 'connected', 'job_id': job_id})}\n\n"

    while time.time() < deadline:
        # Leer todos los eventos nuevos desde el índice actual
        events = r.lrange(key, index, -1)

        if events:
            deadline = time.time() + STREAM_IDLE_TIMEOUT

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