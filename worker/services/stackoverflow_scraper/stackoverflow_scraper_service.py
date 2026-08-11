# worker/services/stackoverflowscraper/stackoverflow_scraper_service.py
"""
Scraper para StackOverflow usando la API pública (sin autenticación).
Documentación: https://api.stackexchange.com/docs
"""
import re
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any

BASE_URL = "https://api.stackexchange.com/2.3"

DEFAULT_HEADERS = {
    "Accept-Encoding": "gzip",
    "User-Agent": "WebScrappingUNAB/1.0 (academic project)",
}


# ---------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------

def _get(endpoint: str, params: dict) -> dict:
    """
    GET con reintentos y manejo de backoff.
    StackExchange devuelve 'backoff' en segundos cuando hay throttle.
    """
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(3):
        try:
            resp = requests.get(
                url,
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            # Respetar backoff de la API
            if "backoff" in data:
                time.sleep(data["backoff"])

            return data

        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise RuntimeError(f"Error en StackExchange API: {e}")
            time.sleep(2 ** attempt)  # exponential backoff

    return {}


def _ts_to_date(ts: int) -> str:
    """Convierte timestamp Unix a string YYYY-MM-DD."""
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _truncate(text: str, max_chars: int) -> str:
    """Limpia HTML y trunca a max_chars caracteres."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_chars] + "..." if len(clean) > max_chars else clean


# ---------------------------------------------------------------
# Función principal: buscar preguntas
# ---------------------------------------------------------------

def search_questions(
    query: str,
    max_results: int = 30,
    tagged: str = "",
    sort: str = "relevance",    # relevance | votes | activity | creation
    min_score: int = 0,
) -> List[Dict[str, Any]]:
    """
    Busca preguntas en StackOverflow por texto libre.

    Returns:
        Lista de dicts con campos:
        title, url, source, score, date, author,
        tags, answer_count, is_answered, body_preview
    """
    results: List[Dict[str, Any]] = []
    page = 1
    page_size = min(max_results, 100)  # API permite max 100 por página

    while len(results) < max_results:
        params = {
            "site":     "stackoverflow",
            "q":        query,
            "sort":     sort,
            "order":    "desc",
            "pagesize": page_size,
            "page":     page,
            "filter":   "withbody",
        }
        if tagged:
            params["tagged"] = tagged

        data  = _get("/search/advanced", params)
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            score = item.get("score", 0)
            if score < min_score:
                continue

            results.append({
                "title":        item.get("title", "Sin título"),
                "url":          item.get("link", "#"),
                "source":       "StackOverflow",
                "score":        score,
                "date":         _ts_to_date(item.get("creation_date", 0)),
                "author":       item.get("owner", {}).get("display_name", "anónimo"),
                "tags":         item.get("tags", []),
                "answer_count": item.get("answer_count", 0),
                "is_answered":  item.get("is_answered", False),
                "body_preview": _truncate(item.get("body", ""), 300),
            })

            if len(results) >= max_results:
                break

        if not data.get("has_more", False):
            break

        page += 1
        time.sleep(0.2)  # Respetar rate limit

    return results


# ---------------------------------------------------------------
# Función secundaria: obtener respuestas de una pregunta
# ---------------------------------------------------------------

def get_answers(
    question_id: int,
    max_answers: int = 5,
) -> List[Dict[str, Any]]:
    """
    Obtiene las respuestas de una pregunta específica.
    Útil para enriquecer el corpus de texto para el LLM.
    """
    params = {
        "site":     "stackoverflow",
        "sort":     "votes",
        "order":    "desc",
        "pagesize": max_answers,
        "filter":   "withbody",
    }
    data    = _get(f"/questions/{question_id}/answers", params)
    answers = []

    for item in data.get("items", []):
        answers.append({
            "answer_id":    item.get("answer_id"),
            "score":        item.get("score", 0),
            "is_accepted":  item.get("is_accepted", False),
            "author":       item.get("owner", {}).get("display_name", "anónimo"),
            "body_preview": _truncate(item.get("body", ""), 300),
        })

    return answers


# ---------------------------------------------------------------
# Función de extracción completa
# ---------------------------------------------------------------

def extract_full_data(
    query: str,
    max_results: int = 30,
) -> Dict[str, Any]:
    """
    Extrae preguntas y construye corpus de texto para el LLM.

    Returns:
        {
            "posts":  [...],   # para la DataTable del frontend
            "corpus": [...]    # textos para wordcloud / grafo / LLM
        }
    """
    posts  = search_questions(query, max_results=max_results)
    corpus: List[str] = []

    for post in posts:
        parts = [post["title"]]
        if post.get("body_preview"):
            parts.append(post["body_preview"])
        corpus.append(" ".join(parts))

    return {
        "posts":  posts,
        "corpus": corpus,
    }