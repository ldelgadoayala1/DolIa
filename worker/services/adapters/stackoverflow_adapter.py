# worker/services/adapters/stackoverflow_adapter.py
"""
Adapta stackoverflow_scraper_service al contrato SourceAdapter, normalizando
sus posts al esquema común (INSTRUCCIONES_IA.md sección 3.4).
"""
from typing import Any, Dict, List

from services.stackoverflow_scraper.stackoverflow_scraper_service import extract_full_data


def _normalize(raw_post: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": raw_post.get("title", "Sin título"),
        "url": raw_post.get("url", "#"),
        "source": "StackOverflow",
        "content": raw_post.get("body_preview", ""),
        "author": raw_post.get("author", "anónimo"),
        "date": raw_post.get("date", "-"),
        "score": raw_post.get("score", 0),
        "tags": raw_post.get("tags", []) or [],
    }


class StackOverflowAdapter:
    name = "stackoverflow"

    def check(self) -> Dict[str, Any]:
        return {"available": True, "name": self.name, "reason": None}

    def search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        extracted = extract_full_data(query, max_results=limit)
        return [_normalize(post) for post in extracted.get("posts", [])]

    def read(self, url: str) -> Dict[str, Any]:
        raise NotImplementedError("StackOverflowAdapter no soporta read()")
