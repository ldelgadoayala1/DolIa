# worker/services/rss_scraper/rss_scraper_service.py
"""
Scraper para RSS/Atom vía el feed de búsqueda público de Google News
(https://news.google.com/rss/search), no una lista fija de feeds: a
diferencia de un feed de blog (que no tiene buscador propio), este endpoint
acepta una query de texto libre y devuelve RSS 2.0 con los artículos más
relevantes — mismo contrato de búsqueda que StackOverflow/GitHub/HN. No
requiere autenticación ni API key.

Reglas de seguridad (INSTRUCCIONES_IA.md sección 3.5 y 6): dominio fijo (no
hay URL controlada por el usuario, no hay SSRF), timeout corto, tamaño de
respuesta acotado (defensa en profundidad contra feeds anómalos/billion
laughs) y sin seguir esta lectura de redirecciones hacia destinos privados
(requests con verify TLS por defecto, sin allow_redirects manual a hosts
arbitrarios).
"""
import re
import time
from email.utils import parsedate_to_datetime
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any

BASE_URL = "https://news.google.com/rss/search"
MAX_QUERY_LENGTH = 200
MAX_RESPONSE_BYTES = 2_000_000  # 2 MB, de sobra para un feed RSS de noticias

DEFAULT_HEADERS = {
    "User-Agent": "WebScrappingUNAB/1.0 (academic project)",
}


# ---------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------

def _get(query: str) -> bytes:
    """
    GET con reintentos, timeout corto y tope de tamaño de respuesta
    (se descarga en streaming y se corta si excede MAX_RESPONSE_BYTES).
    """
    params = {"q": query, "hl": "es-419", "gl": "CL", "ceid": "CL:es"}

    for attempt in range(3):
        try:
            with requests.get(
                BASE_URL, params=params, headers=DEFAULT_HEADERS,
                timeout=10, stream=True,
            ) as resp:
                resp.raise_for_status()
                chunks = []
                total = 0
                for chunk in resp.iter_content(chunk_size=8192):
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise RuntimeError("Respuesta RSS excede el tamaño máximo permitido")
                    chunks.append(chunk)
                return b"".join(chunks)

        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise RuntimeError(f"Error en Google News RSS: {e}")
            time.sleep(2 ** attempt)  # exponential backoff

    raise RuntimeError("Error en Google News RSS: reintentos agotados")


def _rfc2822_to_date(value: str) -> str:
    """Convierte 'Wed, 17 Sep 2026 10:00:00 GMT' (RFC 2822) a 'YYYY-MM-DD'."""
    if not value:
        return "-"
    try:
        return parsedate_to_datetime(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return "-"


def _clean_html(text: str, max_chars: int) -> str:
    """
    El <description> de Google News suele traer HTML (link + fuente).
    Se extrae el texto plano, se colapsan espacios y se trunca.
    """
    plain = BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)
    clean = re.sub(r"\s+", " ", plain).strip()
    return clean[:max_chars] + "..." if len(clean) > max_chars else clean


# ---------------------------------------------------------------
# Función principal: buscar noticias
# ---------------------------------------------------------------

def search_news(
    query: str,
    max_results: int = 30,
) -> List[Dict[str, Any]]:
    """
    Busca artículos de noticias por texto libre vía Google News RSS.

    Returns:
        Lista de dicts con campos:
        title, url, source, score, date, author, tags, body_preview
    """
    query = (query or "").strip()[:MAX_QUERY_LENGTH]
    if not query:
        return []

    xml_bytes = _get(query)
    soup = BeautifulSoup(xml_bytes, "xml")

    results: List[Dict[str, Any]] = []
    for item in soup.find_all("item")[:max_results]:
        title_tag = item.find("title")
        link_tag = item.find("link")
        pubdate_tag = item.find("pubDate")
        source_tag = item.find("source")
        description_tag = item.find("description")

        source_name = source_tag.get_text(strip=True) if source_tag else "-"

        results.append({
            "title": title_tag.get_text(strip=True) if title_tag else "Sin título",
            "url": link_tag.get_text(strip=True) if link_tag else "#",
            "source": "RSS",
            "score": 0,  # RSS no expone una señal de popularidad como votos/puntos
            "date": _rfc2822_to_date(pubdate_tag.get_text(strip=True) if pubdate_tag else ""),
            "author": source_name,  # RSS no trae byline; se usa el medio como referencia
            "tags": [],
            "body_preview": _clean_html(description_tag.get_text() if description_tag else "", 300),
        })

    return results
