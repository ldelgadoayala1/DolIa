from typing import Any, Dict, List

from .prompt_builder import TAGS

DEFAULT_TAG = "Sin clasificar"


def _extract_items(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        for key in ("results", "posts", "annotations", "items", "edges"):
            value = raw.get(key)
            if isinstance(value, list):
                return value

    return []


def normalize_annotations(raw: Dict[str, Any], batch_size: int) -> Dict[int, Dict[str, Any]]:
    """
    Normaliza la respuesta del LLM a un dict {index: {relevance_score, tag, justification}}.
    Tolerante a variaciones de nombre de campo, como en RubricAgent.
    Cualquier índice faltante o inválido simplemente no aparece en el resultado.
    """
    items = _extract_items(raw)
    normalized: Dict[int, Dict[str, Any]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        index = item.get("index")
        if not isinstance(index, int) or not (0 <= index < batch_size):
            continue

        score = (
            item.get("relevance_score")
            or item.get("score")
            or item.get("relevance")
            or 0
        )
        try:
            score = max(0, min(100, int(score)))
        except (TypeError, ValueError):
            score = 0

        tag = (
            item.get("tag")
            or item.get("category")
            or item.get("label")
            or DEFAULT_TAG
        )
        if tag not in TAGS:
            tag = DEFAULT_TAG

        justification = (
            item.get("justification")
            or item.get("feedback")
            or item.get("comment")
            or ""
        )

        normalized[index] = {
            "relevance_score": score,
            "tag": tag,
            "justification": justification,
        }

    return normalized


def normalize_relations(raw: Any, topic_count: int) -> List[Dict[str, Any]]:
    """
    Normaliza la respuesta del LLM a una lista de relaciones válidas entre
    índices de temas. Tolerante a índices/pesos inválidos, pares duplicados
    (en cualquier orden) y relaciones de un tema consigo mismo.
    """
    items = _extract_items(raw)
    relations: List[Dict[str, Any]] = []
    seen_pairs = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        src = item.get("source_index")
        tgt = item.get("target_index")
        if not isinstance(src, int) or not isinstance(tgt, int):
            continue
        if not (0 <= src < topic_count) or not (0 <= tgt < topic_count) or src == tgt:
            continue

        pair = tuple(sorted((src, tgt)))
        if pair in seen_pairs:
            continue

        weight = item.get("weight", 0)
        try:
            weight = max(0, min(100, int(weight)))
        except (TypeError, ValueError):
            weight = 0
        if weight < 30:
            continue

        seen_pairs.add(pair)
        relation = str(item.get("relation") or "")[:120]

        relations.append({
            "source_index": pair[0],
            "target_index": pair[1],
            "weight": weight,
            "relation": relation,
        })

    return relations
