import os
import re
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

import redis
from services.adapters.registry import get_adapter
from services.ai.annotator import annotate_posts
from services.ai.relations import infer_topic_relations
from services.ai.source_planner import PROBE_SIZE, plan_sources

from sse_queue import push_event
from db import JobLog, SearchQuery, get_session, init_db

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

# Tope de posts a pedirle a CADA fuente activa. No se divide max_results entre
# la cantidad de fuentes: repartir en partes iguales le da el mismo cupo a una
# fuente floja (0 resultados) que a una fuerte, y termina capando el pool que
# ve la IA por debajo de max_results aunque una sola fuente pudiera cubrirlo
# entera (ver CLAUDE.md, testeo de los tracks del debut). Este cap es
# independiente de la cantidad de fuentes registradas — acota el costo de
# clasificación por fuente sin que se achique a medida que se agregan
# adaptadores nuevos. La selección final de los max_results mejores posts la
# hace la IA (relevance_score), no el reparto de cupo en el scraping.
# Desde HU-06 es solo el techo: el cupo real de cada fuente lo decide el
# planificador (services/ai/source_planner.py) a partir de un sondeo previo.
PER_SOURCE_CAP = 30


def _run_per_source(adapters: List[Any], fn: Callable[[Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Ejecuta fn(adapter) para cada fuente en paralelo (son llamadas HTTP
    independientes a terceros). Devuelve {nombre: posts | Exception}: la
    falla de una fuente no cancela las demás.
    """
    if not adapters:
        return {}

    def safe(adapter: Any) -> Any:
        try:
            return fn(adapter)
        except Exception as e:
            return e

    with ThreadPoolExecutor(max_workers=len(adapters)) as pool:
        results = pool.map(safe, adapters)
        return {adapter.name: result for adapter, result in zip(adapters, results)}


def _persist_log(job_id: str, stage: str, level: str, message: str, data: Dict[str, Any] | None) -> None:
    """Best-effort: un problema de DB no debe tumbar el pipeline (Redis/SSE sigue siendo la vía crítica)."""
    try:
        with get_session() as session:
            session.add(JobLog(job_id=job_id, stage=stage, level=level, message=message, data=data))
    except Exception as e:
        print(f"[worker] no se pudo escribir log en DB (job_id={job_id}): {e}")


def _update_query(job_id: str, **fields: Any) -> None:
    """Actualiza campos de search_queries. Best-effort, igual que _persist_log."""
    try:
        with get_session() as session:
            search_query = session.get(SearchQuery, job_id)
            if search_query is None:
                return
            for key, value in fields.items():
                setattr(search_query, key, value)
    except Exception as e:
        print(f"[worker] no se pudo actualizar search_queries (job_id={job_id}): {e}")


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
    _persist_log(job_id, stage, "ERROR" if type_ == "error" else "INFO", status, data)


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
    max_results: int = 10,
    posts: List[Dict[str, Any]] | None = None,
    include_graph: bool = True,
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
        # El grafo cuesta una llamada al LLM; se omite si el frontend no lo pide.
        "graph": build_graph(query, posts) if include_graph else None,
        "posts": posts,
    }


def worker_loop():
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    print(f"[worker] starting (log_level={LOG_LEVEL}) redis={REDIS_URL}")
    init_db()

    while True:
        job_item = r.brpop("jobs:queue", timeout=5)
        if not job_item:
            continue

        _, job_id = job_item
        try:
            payload_raw = r.get(f"job:{job_id}:payload")
            if not payload_raw:
                emit(job_id, "load_payload", 100, "Payload no encontrado", type_="error")
                _update_query(
                    job_id,
                    status="error",
                    error_message="Payload no encontrado en Redis (¿TTL expirado?)",
                    completed_at=datetime.now(timezone.utc),
                )
                continue

            payload = json.loads(payload_raw)
            query = payload["query"]
            sources = payload.get("sources", ["stackoverflow"])
            max_results = int(payload.get("max_results", 10))
            include_graph = bool(payload.get("include_graph", True))

            _update_query(job_id, status="running")
            emit(job_id, "planning", 3, "Inicializando búsqueda...")

            active_adapters = []
            for source_name in sources:
                adapter = get_adapter(source_name)
                if adapter is None:
                    emit(job_id, "planning", 4, f"Fuente desconocida: {source_name}",
                         data={"source": source_name})
                    continue
                active_adapters.append(adapter)

            # Techo por fuente: el planificador nunca asigna más que esto.
            per_source_limit = min(max_results, PER_SOURCE_CAP)

            # --- Pre-scraping (HU-06): sondeo barato de cada fuente, sin IA ---
            emit(job_id, "planning", 6,
                 f"Sondeando {len(active_adapters)} fuentes para decidir dónde buscar...")
            probe_results = _run_per_source(
                active_adapters, lambda adapter: adapter.search(query, PROBE_SIZE))

            probes: List[Dict[str, Any]] = []
            for adapter in active_adapters:
                result = probe_results[adapter.name]
                if isinstance(result, Exception):
                    emit(job_id, "planning", 8,
                         f"Fuente {adapter.name} falló en el sondeo, se omite: {result}",
                         data={"source": adapter.name})
                    print(f"[worker] sondeo de {adapter.name} falló job_id={job_id}: {result}")
                    result = []
                probes.append({
                    "name": adapter.name,
                    "description": adapter.description,
                    "posts": result,
                })

            probe_hits = {p["name"]: len(p["posts"]) for p in probes}
            emit(job_id, "planning", 10, "Decidiendo con IA en qué fuentes buscar...",
                 data={"probe_hits": probe_hits})

            allocations, plan_error = plan_sources(query, probes, max_results, per_source_limit)
            if plan_error:
                emit(job_id, "planning", 12,
                     "⚠️ El planificador de IA falló; se reparte según el sondeo",
                     data={"error": plan_error})

            chosen = {name: n for name, n in allocations.items() if n > 0}
            skipped = [name for name, n in allocations.items() if n == 0]
            plan_status = "Plan: " + (", ".join(f"{name} {n}" for name, n in chosen.items())
                                      or "ninguna fuente con resultados")
            if skipped:
                plan_status += f" (omitidas: {', '.join(skipped)})"
            emit(job_id, "planning", 15, plan_status,
                 data={"allocations": allocations, "fallback": plan_error is not None})

            # --- Scraping según el plan ---
            # Si el cupo cabe en lo que ya trajo el sondeo, no se vuelve a
            # consultar esa fuente.
            probe_posts = {p["name"]: p["posts"] for p in probes}
            to_fetch = [a for a in active_adapters
                        if allocations.get(a.name, 0) > len(probe_posts[a.name])]
            if to_fetch:
                emit(job_id, "scraping", 20,
                     f"Consultando {', '.join(a.name for a in to_fetch)}...",
                     data={"sources": [a.name for a in to_fetch]})
            fetch_results = _run_per_source(
                to_fetch, lambda adapter: adapter.search(query, allocations[adapter.name]))

            real_posts: List[Dict[str, Any]] = []
            for adapter in active_adapters:
                limit = allocations.get(adapter.name, 0)
                if limit == 0:
                    continue
                fetched = fetch_results.get(adapter.name, [])
                if isinstance(fetched, Exception):
                    emit(job_id, "scraping", 30,
                         f"Fuente {adapter.name} falló: {fetched} — se usan los resultados del sondeo",
                         data={"source": adapter.name})
                    print(f"[worker] fuente {adapter.name} falló job_id={job_id}: {fetched}")
                    fetched = []
                # El sondeo suele ser un prefijo de la búsqueda completa: se
                # unen ambos sin repetir URL y se corta al cupo asignado.
                source_urls: set = set()
                source_posts: List[Dict[str, Any]] = []
                for post in fetched + probe_posts[adapter.name]:
                    if post.get("url") in source_urls:
                        continue
                    source_urls.add(post.get("url"))
                    source_posts.append(post)
                real_posts.extend(source_posts[:limit])

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
                def on_batch(current: int, total: int) -> None:
                    emit(job_id, "classifying", 55 + round(18 * (current - 1) / total),
                         f"Analizando con IA: lote {current} de {total}...")

                real_posts, annotation_errors = annotate_posts(query, real_posts, on_batch=on_batch)

                if annotation_errors:
                    emit(job_id, "classifying", 60,
                         f"⚠️ {len(annotation_errors)} lote(s) de clasificación fallaron "
                         "tras reintentar (gateway LLM o JSON inválido) — esos posts quedaron "
                         "con relevancia/tag por defecto",
                         data={"batch_errors": annotation_errors})

                flagged_count = sum(1 for p in real_posts if p.get("flagged"))
                real_posts = [p for p in real_posts if not p.get("flagged")]

                # Con varias fuentes activas puede haber más candidatos que
                # max_results (ej. una fuente entregó de más antes de dedupe).
                # Se ordena por relevance_score (ya calculado por la IA) y se
                # corta a max_results — el usuario pidió un total, no un total
                # por fuente.
                real_posts.sort(key=_relevance, reverse=True)
                real_posts = real_posts[:max_results]

                status = f"✅ {len(real_posts)} posts analizados"
                if flagged_count:
                    status += f" ({flagged_count} descartados por contenido inapropiado)"
                emit(job_id, "classifying", 75, status, data={"count": len(real_posts)})

            emit(job_id, "building", 85,
                 "Construyendo grafo de relaciones semánticas..." if include_graph
                 else "Generando nube de palabras...")
            result = run_llm_aggregate(
                query=query,
                posts=real_posts,
                max_results=max_results,
                include_graph=include_graph,
            )
            emit(job_id, "building", 95, "Generando nube de palabras y gráficos...",
                 data={"count": len(real_posts)})

            r.set(f"job:{job_id}:result", json.dumps(result), ex=600)
            r.set(f"job:{job_id}:status", "done", ex=600)

            _update_query(
                job_id,
                status="done",
                summary=result.get("summary"),
                posts_count=len(real_posts),
                completed_at=datetime.now(timezone.utc),
            )
            emit(job_id, "finalize", 100, "Completado", type_="done", data=result)

        except Exception as e:
            msg = str(e)
            emit(job_id, "error", 100, "Error en el worker", type_="error", data={"message": msg})
            _update_query(
                job_id,
                status="error",
                error_message=msg,
                completed_at=datetime.now(timezone.utc),
            )
            print(f"[worker] error job_id={job_id}: {msg}")


if __name__ == "__main__":
    worker_loop()
