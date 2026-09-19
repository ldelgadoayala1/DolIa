# worker/services/adapters/registry.py
"""
Registro explícito de fuentes disponibles (INSTRUCCIONES_IA.md sección 3.2).
No se cargan adaptadores dinámicamente a partir de nombres recibidos por el
usuario: solo lo que está declarado acá queda accesible.
"""
from typing import Dict, Optional

from services.adapters.base import SourceAdapter
from services.adapters.crossref_adapter import CrossRefAdapter
from services.adapters.github_adapter import GitHubAdapter
from services.adapters.hackernews_adapter import HackerNewsAdapter
from services.adapters.rss_adapter import RSSAdapter
from services.adapters.stackoverflow_adapter import StackOverflowAdapter

SOURCE_REGISTRY: Dict[str, SourceAdapter] = {
    "stackoverflow": StackOverflowAdapter(),
    "github": GitHubAdapter(),
    "hackernews": HackerNewsAdapter(),
    "rss": RSSAdapter(),
    "crossref": CrossRefAdapter(),
}


def get_adapter(name: str) -> Optional[SourceAdapter]:
    return SOURCE_REGISTRY.get(name)
