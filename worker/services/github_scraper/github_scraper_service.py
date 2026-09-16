# worker/services/github_scraper/github_scraper_service.py
"""
Scraper para GitHub Issues usando la API pública de búsqueda de GitHub.
Documentación: https://docs.github.com/en/rest/search#search-issues-and-pull-requests
No requiere autenticación; si existe GITHUB_TOKEN se usa para subir el
límite de 10 a 30 req/min, pero nunca se loguea su valor.
"""
import os
import re
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any

BASE_URL = "https://api.github.com"
MAX_QUERY_LENGTH = 200

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

DEFAULT_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "WebScrappingUNAB/1.0 (academic project)",
}
if GITHUB_TOKEN:
    DEFAULT_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


# ---------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------

def _get(endpoint: str, params: dict) -> dict:
    """
    GET con reintentos y manejo de rate limit.
    La Search API de GitHub devuelve 403 (X-RateLimit-Remaining: 0) o 429
    cuando hay throttle, a veces con header Retry-After.
    """
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=10)

            if resp.status_code in (403, 429) and resp.headers.get("X-RateLimit-Remaining") == "0":
                wait = int(resp.headers.get("Retry-After", "5"))
                time.sleep(min(wait, 30))
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise RuntimeError(f"Error en GitHub Search API: {e}")
            time.sleep(2 ** attempt)  # exponential backoff

    raise RuntimeError("Error en GitHub Search API: rate limit persistente")


def _iso_to_date(iso_str: str) -> str:
    """Convierte 'YYYY-MM-DDTHH:MM:SSZ' a 'YYYY-MM-DD'."""
    if not iso_str:
        return "-"
    return iso_str[:10]


def _truncate(text: str, max_chars: int) -> str:
    """Colapsa espacios y trunca a max_chars caracteres (body es markdown, no HTML)."""
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean[:max_chars] + "..." if len(clean) > max_chars else clean


# ---------------------------------------------------------------
# Función principal: buscar issues
# ---------------------------------------------------------------

def search_issues(
    query: str,
    max_results: int = 30,
    sort: str = "best-match",
    order: str = "desc",
) -> List[Dict[str, Any]]:
    """
    Busca issues (sin pull requests) en repos públicos de GitHub por texto libre.

    Returns:
        Lista de dicts con campos:
        title, url, source, score, date, author, tags, body_preview
    """
    query = (query or "").strip()[:MAX_QUERY_LENGTH]

    results: List[Dict[str, Any]] = []
    page = 1
    page_size = min(max_results, 100)  # API permite max 100 por página

    while len(results) < max_results:
        params = {
            "q": f"{query} is:issue",
            "sort": sort,
            "order": order,
            "per_page": page_size,
            "page": page,
        }

        data = _get("/search/issues", params)
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            labels = item.get("labels") or []
            results.append({
                "title": item.get("title", "Sin título"),
                "url": item.get("html_url", "#"),
                "source": "GitHub",
                "score": item.get("comments", 0),
                "date": _iso_to_date(item.get("created_at", "")),
                "author": (item.get("user") or {}).get("login", "anónimo"),
                "tags": [
                    label.get("name", "") if isinstance(label, dict) else str(label)
                    for label in labels
                ],
                "body_preview": _truncate(item.get("body") or "", 300),
            })

            if len(results) >= max_results:
                break

        if page * page_size >= data.get("total_count", 0):
            break

        page += 1
        time.sleep(0.2)  # respetar rate limit

    return results
