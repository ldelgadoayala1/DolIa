import os
import re
import json
from collections import Counter, defaultdict
from typing import Dict, Any, List

import redis
from services.stackoverflow_scraper.stackoverflow_scraper_service import extract_full_data
from services.ai.annotator import annotate_posts
from services.ai.relations import infer_topic_relations

from sse_queue import push_event

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for",
    "of", "and", "or", "with", "how", "what", "why", "do", "does", "did", "can",
    "could", "i", "my", "this", "that", "it", "its", "not", "using", "use", "from",
    "when", "error", "issue", "problem", "get", "getting", "have", "has", "be",
    "but", "as", "by", "you", "your", "if", "so", "then", "than", "there", "these",
    "those", "will", "would", "should", "about", "into", "after", "before", "same",
}

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


def _relevance(post: Dict[str, Any]) -> float:
    score = post.get("relevance_score")
    return float(score) if isinstance(score, (int, float)) else 50.0


def build_wordcloud(posts: List[Dict[str, Any]], max_words: int = 25) -> List[Dict[str, Any]]:
    """
    Frecuencia ponderada por relevance_score (LLM): tags de StackOverflow
    (señal limpia) pesan más que palabras sueltas del título.
    """
    counter: Counter = Counter()

    for post in posts:
        weight = _relevance(post) / 100 + 0.2

        for tag in post.get("tags", []) or []:
            counter[tag.lower()] += 3 * weight

        for word in re.findall(r"[a-zA-Záéíóúñ]{3,}", (post.get("title") or "").lower()):
            if word in STOPWORDS:
                continue
            counter[word] += weight

    return [
        {"word": word, "weight": round(value, 2)}
        for word, value in counter.most_common(max_words)
    ]


def _cooccurrence_relations(posts: List[Dict[str, Any]], topics: List[str]) -> List[Dict[str, Any]]:
    """
    Fallback sin LLM: conecta temas que aparecen juntos en el mismo post.
    Se usa solo si infer_topic_relations() falla o no encuentra relaciones.
    """
    topic_set = set(topics)
    pair_weight: Dict[tuple, int] = defaultdict(int)

    for post in posts:
        post_topics = sorted(set(t for t in (post.get("tags") or []) if t in topic_set))
        for i in range(len(post_topics)):
            for j in range(i + 1, len(post_topics)):
                pair_weight[(post_topics[i], post_topics[j])] += 1

    return [
        {"source": a, "target": b, "weight": min(100, w * 25), "relation": "aparecen juntos en los resultados"}
        for (a, b), w in pair_weight.items()
    ]


def build_graph(query: str, posts: List[Dict[str, Any]], max_topics: int = 15) -> Dict[str, Any]:
    """
    Grafo semántico entre temas (tags de StackOverflow): las aristas y su
    peso/etiqueta las decide el LLM (infer_topic_relations), no reglas fijas.
    Si el LLM no puede resolver relaciones, cae a un grafo de co-ocurrencia
    (temas que aparecen juntos en el mismo post) para no dejar el grafo vacío.
    """
    topic_weight: Counter = Counter()
    for post in posts:
        for topic in (post.get("tags") or [])[:3]:
            topic_weight[topic] += 1

    top_topics = [topic for topic, _ in topic_weight.most_common(max_topics)]

    relations = infer_topic_relations(query, top_topics)
    if not relations:
        relations = _cooccurrence_relations(posts, top_topics)

    nodes: List[Dict[str, Any]] = [
        {"id": topic, "label": topic, "weight": topic_weight[topic], "group": "topic"}
        for topic in top_topics
    ]

    edges: List[Dict[str, Any]] = [
        {
            "id": f"e_{i}",
            "source": rel["source"],
            "target": rel["target"],
            "weight": rel["weight"],
            "relation": rel.get("relation", ""),
        }
        for i, rel in enumerate(relations)
    ]

    return {"nodes": nodes, "edges": edges}


def run_llm_aggregate(
    query: str,
    texts: List[str],
    max_results: int = 10,
    posts: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Retorna estructura para el frontend:
      - wordcloud: [{word, weight}, ...]  (ponderado por relevance_score del LLM)
      - graph: {nodes:[...], edges:[...]}  (temas de SO <-> categorías del LLM)
      - summary: string
      - posts: [{title, url, source, score, date, author, relevance_score, tag}]
    """
    posts = posts or []

    if posts:
        top_categories = Counter(p.get("tag") or "Sin clasificar" for p in posts).most_common(3)
        categories_str = ", ".join(f"{c} ({n})" for c, n in top_categories)
        summary = f"{len(posts)} resultados para \"{query}\". Categorías principales: {categories_str}."
    else:
        summary = f"Sin resultados para \"{query}\"."

    return {
        "summary": summary,
        "wordcloud": build_wordcloud(posts),
        "graph": build_graph(query, posts),
        "posts": posts,
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

            emit(job_id, "scraping", 5, "Inicializando búsqueda...")

            texts: List[str] = []
            real_posts: List[Dict[str, Any]] = []

            if "stackoverflow" in sources:
                emit(job_id, "scraping", 20, "Consultando StackOverflow API...")
                extracted = extract_full_data(query, max_results=max_results)
                real_posts = extracted.get("posts", [])
                texts = extracted.get("corpus", [])

                seen_urls: set = set()
                deduped_posts: List[Dict[str, Any]] = []
                for post in real_posts:
                    url = post.get("url")
                    if url in seen_urls or not (post.get("title") or "").strip():
                        continue
                    seen_urls.add(url)
                    deduped_posts.append(post)
                real_posts = deduped_posts

                emit(job_id, "scraping", 45, f"✅ {len(real_posts)} resultados obtenidos",
                     data={"count": len(real_posts)})

            if real_posts:
                emit(job_id, "classifying", 55,
                     "Analizando relevancia y filtrando contenido inapropiado con IA...")
                real_posts = annotate_posts(query, real_posts)

                flagged_count = sum(1 for p in real_posts if p.get("flagged"))
                real_posts = [p for p in real_posts if not p.get("flagged")]

                status = f"✅ {len(real_posts)} posts analizados"
                if flagged_count:
                    status += f" ({flagged_count} descartados por contenido inapropiado)"
                emit(job_id, "classifying", 75, status, data={"count": len(real_posts)})

            emit(job_id, "building", 85, "Construyendo grafo de relaciones semánticas...")
            result = run_llm_aggregate(
                query=query,
                texts=texts,
                posts=real_posts,
                max_results=max_results,
            )
            emit(job_id, "building", 95, "Generando nube de palabras y gráficos...",
                 data={"count": len(real_posts)})

            r.set(f"job:{job_id}:result", json.dumps(result), ex=600)
            r.set(f"job:{job_id}:status", "done", ex=600)

            emit(job_id, "finalize", 100, "Completado", type_="done", data=result)

        except Exception as e:
            msg = str(e)
            emit(job_id, "error", 100, "Error en el worker", type_="error", data={"message": msg})
            print(f"[worker] error job_id={job_id}: {msg}")


if __name__ == "__main__":
    worker_loop()
