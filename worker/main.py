import os
import time
import json
import redis
from typing import Dict, Any, List

from sse_queue import push_event  # lo añadiremos desde worker (abajo)

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


# -----------------------------
# MVP "scraping" (placeholder real)
# -----------------------------
def scrape_reddit(query: str, max_results: int) -> List[str]:
    # Placeholder: reemplazar por scraping real
    return [f"reddit result {i+1} for {query}" for i in range(max_results)]


def scrape_stackoverflow(query: str, max_results: int) -> List[str]:
    return [f"stackoverflow answer {i+1} about {query}" for i in range(max_results)]


# -----------------------------
# MVP "LLM aggregation" placeholder
# -----------------------------
def run_llm_aggregate(query: str, texts: List[str]) -> Dict[str, Any]:
    """
    Retorna estructura para el frontend:
      - wordcloud: [{word, weight}, ...]
      - graph: {nodes:[...], edges:[...]}
      - summary: string
    """
    # Para demo: usamos palabras derivadas de query
    base = [w for w in query.lower().split() if w.strip()]
    if not base:
        base = ["dolencia"]

    wordcloud = []
    for i, w in enumerate(base):
        wordcloud.append({"word": w, "weight": 10 + i * 3})
    # palabras extra
    for i in range(6):
        wordcloud.append({"word": f"tema{i+1}", "weight": 7 - i * 0.7})

    nodes = []
    edges = []
    # nodos
    for i in range(len(base)):
        nodes.append({"id": f"topic_{i}", "label": base[i]})
    for j in range(5):
        nodes.append({"id": f"source_{j}", "label": f"fuente{j+1}"})

    # edges: conectamos topics con sources
    topic_count = len(base)
    for i in range(topic_count):
        for j in range(5):
            edges.append({
                "id": f"e_{i}_{j}",
                "source": f"topic_{i}",
                "target": f"source_{j}",
                "weight": 1 + (i + j) % 4
            })

    return {
        "summary": f"Resumen MVP para: {query}",
        "wordcloud": wordcloud,
        "graph": {"nodes": nodes, "edges": edges},
    }


def worker_loop():
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    print(f"[worker] starting (log_level={LOG_LEVEL}) redis={REDIS_URL}")
    while True:
        # Espera job_id
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
            sources = payload.get("sources", ["reddit", "stackoverflow"])
            max_results = int(payload.get("max_results", 30))

            emit(job_id, "init", 1, "Inicializando búsqueda...")

            # Etapa 1: scraping
            emit(job_id, "scrape", 10, f"Consultando fuentes: {', '.join(sources)}")
            texts: List[str] = []

            if "reddit" in sources:
                emit(job_id, "scrape", 25, "Scrapeando Reddit...")
                texts.extend(scrape_reddit(query, max_results=max_results // 2))
                time.sleep(0.5)

            if "stackoverflow" in sources:
                emit(job_id, "scrape", 45, "Scrapeando StackOverflow...")
                texts.extend(scrape_stackoverflow(query, max_results=max_results // 2))
                time.sleep(0.5)

            emit(job_id, "scrape", 60, f"Recolectados {len(texts)} documentos")

            # Etapa 2: LLM
            emit(job_id, "llm", 70, "Agrupando y clasificando con IA (MVP)...")
            time.sleep(1.0)

            # En el futuro: aquí conectamos llm_config.json + gemma 4 real
            result = run_llm_aggregate(query=query, texts=texts)

            # Guardar resultado
            r.set(f"job:{job_id}:result", json.dumps(result))
            r.set(f"job:{job_id}:status", "done")

            emit(job_id, "finalize", 100, "Completado", type_="done", data=result)

        except Exception as e:
            msg = str(e)
            emit(job_id, "error", 100, "Error en el worker", type_="error", data={"message": msg})
            print(f"[worker] error job_id={job_id}: {msg}")


if __name__ == "__main__":
    worker_loop()