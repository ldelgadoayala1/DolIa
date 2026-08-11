import os
import time
import json
from typing import Dict, Any, List

import redis
from services.stackoverflow_scraper.stackoverflow_scraper_service import extract_full_data

from sse_queue import push_event

LOG_LEVEL = os.getenv("WORKER_LOG_LEVEL", "INFO")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def emit(job_id: str, stage: str, progress: int, status: str, type_: str = "progress", data: Dict[str, Any] | None = None):
    event = {
        "stage": stage,
        "progress": progress,
        "status": status,
        "type": type_,
    }
    if data is not None:
        event["data"] = data
    push_event(job_id, event)


def run_llm_aggregate(
    query: str,
    texts: List[str],
    max_results: int = 10,
    posts: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Retorna estructura para el frontend:
      - wordcloud: [{word, weight}, ...]
      - graph: {nodes:[...], edges:[...]}
      - summary: string
      - posts: [{title, url, source, score, date, author}]
    """
    base = [w for w in query.lower().split() if w.strip()]
    if not base:
        base = ["dolencia"]

    wordcloud: List[Dict[str, Any]] = []
    for i, w in enumerate(base):
        wordcloud.append({"word": w, "weight": 10 + i * 3})
    for i in range(6):
        wordcloud.append({"word": f"tema{i+1}", "weight": 7 - i * 0.7})

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for i in range(len(base)):
        nodes.append({"id": f"topic_{i}", "label": base[i]})
    for j in range(5):
        nodes.append({"id": f"source_{j}", "label": f"fuente{j+1}"})

    topic_count = len(base)
    for i in range(topic_count):
        for j in range(5):
            edges.append({
                "id": f"e_{i}_{j}",
                "source": f"topic_{i}",
                "target": f"source_{j}",
                "weight": 1 + (i + j) % 4,
            })

    return {
        "summary": f"Resumen MVP para: {query}",
        "wordcloud": wordcloud,
        "graph": {"nodes": nodes, "edges": edges},
        "posts": posts or [],
    }


def worker_loop():
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    print(f"[worker] starting (log_level={LOG_LEVEL}) redis={REDIS_URL}")

    while True:
        job_item = r.brpop("jobs:queue", timeout=5)
        if not job_item:
            continue

        _, job_id = job_item
        try:
            payload_raw = r.get(f"job:{job_id}:payload")
            if not payload_raw:
                emit(job_id, "load_payload", 100, "Payload no encontrado", type_="error")
                continue

            payload = json.loads(payload_raw)
            query = payload["query"]
            sources = payload.get("sources", ["stackoverflow"])
            max_results = int(payload.get("max_results", 30))

            emit(job_id, "init", 1, "Inicializando búsqueda...")

            texts: List[str] = []
            real_posts: List[Dict[str, Any]] = []

            if "stackoverflow" in sources:
                emit(job_id, "scrape", 20, "Consultando StackOverflow API...")
                extracted = extract_full_data(query, max_results=max_results)
                real_posts = extracted.get("posts", [])
                texts = extracted.get("corpus", [])
                emit(job_id, "scrape", 60, f"✅ {len(real_posts)} resultados obtenidos")

            emit(job_id, "llm", 70, "Procesando y generando resultados...")
            time.sleep(1.0)

            result = run_llm_aggregate(
                query=query,
                texts=texts,
                posts=real_posts,
                max_results=max_results,
            )

            r.set(f"job:{job_id}:result", json.dumps(result), ex=600)
            r.set(f"job:{job_id}:status", "done", ex=600)

            emit(job_id, "finalize", 100, "Completado", type_="done", data=result)

        except Exception as e:
            msg = str(e)
            emit(job_id, "error", 100, "Error en el worker", type_="error", data={"message": msg})
            print(f"[worker] error job_id={job_id}: {msg}")


if __name__ == "__main__":
    worker_loop()
