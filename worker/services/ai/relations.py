from typing import Any, Dict, List

from .llm_client import call_llm_json
from .prompt_builder import GRAPH_SYSTEM_PROMPT, build_relations_prompt
from .response_parser import normalize_relations


def infer_topic_relations(query: str, topics: List[str]) -> List[Dict[str, Any]]:
    """
    Le pide al LLM que identifique relaciones semánticas entre los temas
    (tags) más frecuentes de los resultados, para construir un grafo real
    en vez de un árbol fijo tema→categoría. Si el LLM falla, retorna lista
    vacía en vez de interrumpir el job (el caller decide el fallback).
    """
    if len(topics) < 2:
        return []

    try:
        prompt = build_relations_prompt(query, topics)
        raw_response = call_llm_json(GRAPH_SYSTEM_PROMPT, prompt)
        relations = normalize_relations(raw_response, topic_count=len(topics))
    except Exception as e:
        print(f"[ai] error infiriendo relaciones de grafo: {e}")
        return []

    return [
        {
            "source": topics[r["source_index"]],
            "target": topics[r["target_index"]],
            "weight": r["weight"],
            "relation": r["relation"],
        }
        for r in relations
    ]
