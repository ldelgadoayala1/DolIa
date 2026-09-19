"""
Catálogo de proveedores de búsqueda. Ver Historias_Usuario.csv para el
detalle de cada HU y CLAUDE.md ("Resumen ejecutivo") para el estado real
de cada conector al momento de escribir esto.
"""

from .database import get_session
from .models import SearchProvider

PROVIDERS = [
    dict(
        slug="stackoverflow",
        display_name="StackOverflow",
        status="active",
        description="API pública de StackExchange. Única fuente activa hoy en el pipeline.",
        rate_limit_info="10000 req/día sin auth (300/día por IP sin key); ~30 req/seg máx.",
        requires_auth=False,
    ),
    dict(
        slug="github",
        display_name="GitHub Issues",
        status="active",
        description="HU-03: issues de GitHub (excluye pull requests) vía la Search API pública.",
        rate_limit_info="Search API: 10 req/min sin auth, 30 req/min con GITHUB_TOKEN (opcional).",
        requires_auth=False,
    ),
    dict(
        slug="hackernews",
        display_name="Hacker News",
        status="active",
        description="HU-04: stories de Hacker News vía la API pública de búsqueda de Algolia.",
        rate_limit_info="Sin límite documentado; API pública sin autenticación.",
        requires_auth=False,
    ),
    dict(
        slug="rss",
        display_name="RSS/Atom (Google News)",
        status="active",
        description=(
            "Fase 2 de INSTRUCCIONES_IA.md: búsqueda de noticias vía el feed público "
            "de Google News RSS (news.google.com/rss/search), sin lista curada de feeds."
        ),
        rate_limit_info="Sin límite documentado; endpoint público sin autenticación.",
        requires_auth=False,
    ),
    dict(
        slug="crossref",
        display_name="CrossRef",
        status="active",
        description=(
            "Literatura académica vía la API pública de CrossRef (api.crossref.org), "
            "búsqueda de texto libre real. Priorizada para los tracks de impacto social "
            "del debut (ver CLAUDE.md, 'Testeo contra los tracks del debut')."
        ),
        rate_limit_info="Sin límite estricto documentado; API pública sin autenticación.",
        requires_auth=False,
    ),
    dict(
        slug="elsevier_scopus",
        display_name="Elsevier / Scopus / ScienceDirect",
        status="pending",
        description=(
            "HU-02: pendiente confirmar acceso institucional UNAB a la API de Elsevier "
            "antes de implementar el conector."
        ),
        rate_limit_info="Depende del plan institucional UNAB (por confirmar).",
        requires_auth=True,
    ),
    dict(
        slug="twitter",
        display_name="X / Twitter",
        status="blocked",
        description=(
            "HU-01: implementado y revertido — el X Developer Portal exige método de pago "
            "incluso en el tier gratuito."
        ),
        rate_limit_info="N/A — bloqueado por billing, no por rate limit.",
        requires_auth=True,
    ),
]


def seed_providers() -> None:
    """Inserta o actualiza el catálogo de proveedores (upsert por slug). Idempotente."""
    with get_session() as session:
        for data in PROVIDERS:
            existing = session.get(SearchProvider, data["slug"])
            if existing:
                for key, value in data.items():
                    if key != "slug":
                        setattr(existing, key, value)
            else:
                session.add(SearchProvider(**data))
