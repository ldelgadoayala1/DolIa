# worker/services/adapters/crossref_adapter.py
"""
Adapta crossref_scraper_service al contrato SourceAdapter, normalizando sus
posts al esquema común (INSTRUCCIONES_IA.md sección 3.4).
"""
from typing import Any, Dict, List

from services.crossref_scraper.crossref_scraper_service import search_works


def _normalize(raw_post: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": raw_post.get("title", "Sin título"),
        "url": raw_post.get("url", "#"),
        "source": "CrossRef",
        "content": raw_post.get("body_preview", ""),
        "author": raw_post.get("author", "-"),
        "date": raw_post.get("date", "-"),
        "score": raw_post.get("score", 0),
        "tags": raw_post.get("tags", []) or [],
    }


class CrossRefAdapter:
    name = "crossref"

    def check(self) -> Dict[str, Any]:
        return {"available": True, "name": self.name, "reason": None}

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        return [_normalize(post) for post in search_works(query, max_results=limit)]

    def read(self, url: str) -> Dict[str, Any]:
        raise NotImplementedError("CrossRefAdapter no soporta read()")
