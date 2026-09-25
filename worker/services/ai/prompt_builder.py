from typing import Any, Dict, List

TAGS = [
    "Solucion",
    "Explicacion conceptual",
    "Error/Bug",
    "Advertencia",
    "Herramienta/Alternativa",
    "Otro",
]

SYSTEM_PROMPT = """
Eres un clasificador automático de resultados de búsqueda técnica.

Tu única tarea es responder JSON válido.

NO expliques.
NO converses.
NO des ejemplos.
NO escribas markdown.

La respuesta DEBE ser JSON válido.
"""


def build_annotation_prompt(query: str, posts_batch: List[Dict[str, Any]]) -> str:
    """
    Arma el prompt para que el LLM evalúe relevancia y asigne un tag
    semántico a cada post del lote, respecto al tema buscado.
    """
    formatted_posts = "\n\n".join(
        f"""
Post {i}:
Título: {post.get("title", "")}
Extracto: {post.get("content", "")}
"""
        for i, post in enumerate(posts_batch)
    )

    tags_list = ", ".join(TAGS)

    prompt = f"""
Analiza los siguientes resultados de búsqueda (posts de StackOverflow)
respecto al tema buscado por el usuario.

TEMA BUSCADO:
{query}

Para cada post, evalúa:
1. relevance_score: qué tan relevante es el post respecto al tema buscado,
   de 0 a 100 (0 = nada relevante, 100 = totalmente relevante).
2. tag: una etiqueta semántica que describa el tipo de contenido del post.
   Debe ser exactamente una de estas opciones: {tags_list}.
3. flagged: true si el título o el extracto contienen lenguaje ofensivo,
   vulgar, discriminatorio o inapropiado; false en caso contrario.

POSTS:
{formatted_posts}

Devuelve SOLO JSON válido, sin markdown, sin texto fuera del JSON.
El JSON debe ser parseable directamente con json.loads().

FORMATO JSON ESPERADO:
{{
    "results": [
        {{
            "index": 0,
            "relevance_score": 85,
            "tag": "Solucion",
            "flagged": false
        }},
        "repetir para cada post del lote, usando su índice..."
    ]
}}
"""

    return prompt


PLANNER_SYSTEM_PROMPT = """
Eres un planificador que decide en qué fuentes de información buscar.

Tu única tarea es responder JSON válido.

NO expliques.
NO converses.
NO des ejemplos.
NO escribas markdown.

La respuesta DEBE ser JSON válido.
"""


def build_planning_prompt(
    query: str,
    sources: List[Dict[str, Any]],
    budget: int,
    per_source_cap: int,
) -> str:
    """
    Arma el prompt para que el LLM reparta un presupuesto de posts entre las
    fuentes (HU-06). Cada fuente llega con su descripción y los títulos que
    devolvió el sondeo previo: el LLM decide viendo evidencia real, no solo
    el nombre de la fuente (con solo el nombre adivinaba mal).
    `sources`: [{"name", "description", "hits", "probe_size", "titles"}].
    """
    blocks = []
    for source in sources:
        titles = "\n".join(f"  - {title}" for title in source["titles"]) or "  (sin resultados)"
        blocks.append(
            f"""Fuente: {source["name"]}
Descripción: {source["description"]}
Resultados del sondeo: {source["hits"]} de {source["probe_size"]} pedidos
Títulos de muestra:
{titles}"""
        )
    formatted_sources = "\n\n".join(blocks)

    prompt = f"""
El usuario quiere investigar un tema. Antes de descargar resultados, se hizo
un sondeo rápido en cada fuente. Decide cuántos posts pedirle a cada fuente
para obtener los resultados más relevantes sin descargar contenido inútil.

TEMA BUSCADO:
{query}

FUENTES:
{formatted_sources}

Reglas:
- Reparte en total aproximadamente {budget} posts entre las fuentes.
- Máximo {per_source_cap} posts por fuente.
- Asigna 0 a las fuentes cuyos títulos de muestra no tienen relación con el
  tema buscado, aunque hayan devuelto resultados.
- Asigna más posts a las fuentes cuyos títulos de muestra son más relevantes.
- Usa exactamente los nombres de fuente indicados arriba.

Devuelve SOLO JSON válido, sin markdown, sin texto fuera del JSON.
El JSON debe ser parseable directamente con json.loads().

FORMATO JSON ESPERADO:
{{
    "allocations": [
        {{"source": "nombre_fuente", "posts": 10}},
        "repetir para cada fuente..."
    ]
}}
"""

    return prompt


GRAPH_SYSTEM_PROMPT = """
Eres un analista que identifica relaciones semánticas entre temas técnicos.

Tu única tarea es responder JSON válido.

NO expliques.
NO converses.
NO des ejemplos.
NO escribas markdown.

La respuesta DEBE ser JSON válido.
"""


def build_relations_prompt(query: str, topics: List[str]) -> str:
    """
    Arma el prompt para que el LLM identifique relaciones semánticas entre
    los temas (tags) más frecuentes de los resultados, para construir un
    grafo real en vez de un árbol fijo tema→categoría.
    """
    numbered_topics = "\n".join(f"{i}: {topic}" for i, topic in enumerate(topics))

    prompt = f"""
Estos son los temas/tags principales extraídos de resultados de búsqueda
sobre el tema buscado por el usuario.

TEMA BUSCADO:
{query}

TEMAS (usa el índice numérico para referirte a cada uno):
{numbered_topics}

Identifica relaciones semánticas relevantes ENTRE ESTOS TEMAS (no con el tema
buscado). Para cada par de temas relacionados, evalúa:
1. weight: fuerza de la relación, de 0 a 100 (0 = sin relación, 100 = fuertemente relacionados).
2. relation: una frase muy corta que describa el tipo de relación
   (ej. "se usa junto con", "alternativa de", "causa típica de error en").

Reglas:
- Usa los índices numéricos para referirte a los temas (source_index, target_index).
- Solo incluye pares con weight >= 30.
- No repitas el mismo par en ambos sentidos.
- No incluyas relaciones de un tema consigo mismo.
- Máximo 25 relaciones, prioriza las más fuertes.

Devuelve SOLO JSON válido, sin markdown, sin texto fuera del JSON.
El JSON debe ser parseable directamente con json.loads().

FORMATO JSON ESPERADO:
{{
    "edges": [
        {{"source_index": 0, "target_index": 3, "weight": 75, "relation": "se usa junto con"}},
        "repetir para cada relación identificada..."
    ]
}}
"""

    return prompt
