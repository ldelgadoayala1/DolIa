# worker/services/hackernews_scraper/hackernews_scraper_service.py
"""
Scraper para Hacker News usando la API pública de búsqueda de Algolia
(https://hn.algolia.com/api/v1/search), no la Firebase API oficial: esta
última no soporta búsqueda por texto libre y obligaría a resolver ids uno
por uno. No requiere autenticación ni token.
"""
import re
import time
import requests
from typing import List, Dict, Any

BASE_URL = "https://hn.algolia.com/api/v1"
MAX_QUERY_LENGTH = 200
MAX_PAGE_SIZE = 100  # tope razonable por página, la API permite más


def _get(endpoint: str, params: dict) -> dict:
    """GET con reintentos y backoff exponencial, timeout corto por request."""
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise RuntimeError(f"Error en Hacker News Search API: {e}")
            time.sleep(2 ** attempt)

    raise RuntimeError("Error en Hacker News Search API: reintentos agotados")


def _iso_to_date(iso_str: str) -> str:
    """Convierte 'YYYY-MM-DDTHH:MM:SS.000Z' a 'YYYY-MM-DD'."""
    if not iso_str:
        return "-"
    return iso_str[:10]


def _truncate(text: str, max_chars: int) -> str:
    """Colapsa espacios y trunca a max_chars caracteres."""
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[:max_chars] + "..." if len(clean) > max_chars else clean


def search_stories(
    query: str,
    max_results: int = 30,
) -> List[Dict[str, Any]]:
    """
    Busca stories (excluye comentarios) en Hacker News por texto libre.

    Returns:
        Lista de dicts con campos:
        title, url, source, score, date, author, tags, body_preview
    """
    query = (query or "").strip()[:MAX_QUERY_LENGTH]

    results: List[Dict[str, Any]] = []
    page = 0
    page_size = min(max_results, MAX_PAGE_SIZE)

    while len(results) < max_results:
        params = {
            "query": query,
            "tags": "story",
            "hitsPerPage": page_size,
            "page": page,
        }

        data = _get("/search", params)
        hits = data.get("hits", [])

        if not hits:
            break

        for hit in hits:
            object_id = hit.get("objectID")
            hn_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else "#"

            results.append({
                "title": hit.get("title") or "Sin título",
                "url": hit.get("url") or hn_url,
                "source": "HackerNews",
                "score": hit.get("points", 0) or 0,
                "date": _iso_to_date(hit.get("created_at", "")),
                "author": hit.get("author", "anónimo"),
                "tags": [],
                "body_preview": _truncate(hit.get("story_text") or "", 300),
            })

            if len(results) >= max_results:
                break

        if page + 1 >= data.get("nbPages", 0):
            break

        page += 1
        time.sleep(0.2)  # margen prudente, sin límite documentado por Algolia HN

    return results
