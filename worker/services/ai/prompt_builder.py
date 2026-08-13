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
Extracto: {post.get("body_preview", "")}
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
4. justification: una frase corta explicando el score y el tag asignados.

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
            "flagged": false,
            "justification": "Explica directamente cómo resolver el problema buscado."
        }},
        "repetir para cada post del lote, usando su índice..."
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
