# worker/services/crossref_scraper/crossref_scraper_service.py
"""
Scraper para literatura académica vía la API pública de CrossRef
(https://api.crossref.org/works). Búsqueda de texto libre real (no
palabras clave exactas contra un índice literal como StackOverflow/GitHub/HN),
gratuita y sin autenticación — cubre journals de estudios de género, economía
del cuidado, discapacidad y ética de IA, relevantes para los tracks de
impacto social del debut (ver CLAUDE.md "Testeo contra los tracks del
debut").

Reglas de seguridad (INSTRUCCIONES_IA.md sección 3.5 y 6): dominio fijo (no
hay URL controlada por el usuario, no hay SSRF), timeout corto, `rows`
acotado (limita el tamaño de la respuesta) y `select` para pedir solo los
campos que se usan.
"""
import re
import time
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any

BASE_URL = "https://api.crossref.org/works"
MAX_QUERY_LENGTH = 200
MAX_ROWS = 100  # tope razonable por request, la API permite hasta 1000
SELECT_FIELDS = "DOI,title,author,published,container-title,URL,abstract,subject,score"

DEFAULT_HEADERS = {
    "User-Agent": "WebScrappingUNAB/1.0 (academic project; https://github.com/)",
}


def _get(params: dict) -> dict:
    """GET con reintentos y backoff exponencial, timeout corto."""
    for attempt in range(3):
        try:
            resp = requests.get(BASE_URL, params=params, headers=DEFAULT_HEADERS, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise RuntimeError(f"Error en CrossRef API: {e}")
            time.sleep(2 ** attempt)

    raise RuntimeError("Error en CrossRef API: reintentos agotados")


def _date_from_parts(published: Dict[str, Any]) -> str:
    """Convierte 'date-parts': [[2024, 3, 15]] a 'YYYY-MM-DD' (o 'YYYY-MM'/'YYYY' si faltan campos)."""
    parts = (published or {}).get("date-parts") or [[]]
    parts = parts[0] if parts else []
    if not parts:
        return "-"
    padded = [f"{parts[0]:04d}"]
    if len(parts) > 1:
        padded.append(f"{parts[1]:02d}")
    if len(parts) > 2:
        padded.append(f"{parts[2]:02d}")
    return "-".join(padded)


def _clean_abstract(text: str, max_chars: int) -> str:
    """El abstract de CrossRef viene como XML JATS (<jats:p>...</jats:p>); se extrae texto plano."""
    plain = BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)
    clean = re.sub(r"\s+", " ", plain).strip()
    return clean[:max_chars] + "..." if len(clean) > max_chars else clean


def _format_authors(authors: List[Dict[str, Any]]) -> str:
    if not authors:
        return "-"
    first = authors[0]
    name = " ".join(part for part in [first.get("given"), first.get("family")] if part).strip()
    name = name or "-"
    return f"{name} et al." if len(authors) > 1 else name


def search_works(
    query: str,
    max_results: int = 30,
) -> List[Dict[str, Any]]:
    """
    Busca literatura académica por texto libre en CrossRef.

    Returns:
        Lista de dicts con campos:
        title, url, source, score, date, author, tags, body_preview
    """
    query = (query or "").strip()[:MAX_QUERY_LENGTH]
    if not query:
        return []

    params = {
        "query": query,
        "rows": min(max_results, MAX_ROWS),
        "select": SELECT_FIELDS,
    }

    data = _get(params)
    items = (data.get("message") or {}).get("items", [])

    results: List[Dict[str, Any]] = []
    for item in items[:max_results]:
        titles = item.get("title") or []
        doi = item.get("DOI")
        url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "#")
        container = item.get("container-title") or []
        abstract = _clean_abstract(item.get("abstract", ""), 300)
        if not abstract and container:
            abstract = container[0]

        results.append({
            "title": titles[0] if titles else "Sin título",
            "url": url,
            "source": "CrossRef",
            "score": round(item.get("score") or 0),
            "date": _date_from_parts(item.get("published")),
            "author": _format_authors(item.get("author") or []),
            "tags": (item.get("subject") or [])[:5],
            "body_preview": abstract,
        })

    return results
