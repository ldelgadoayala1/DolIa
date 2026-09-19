from typing import Any, Dict, List, Tuple

from .llm_client import call_llm_json
from .prompt_builder import SYSTEM_PROMPT, build_annotation_prompt
from .response_parser import DEFAULT_TAG, normalize_annotations


def annotate_posts(
    query: str,
    posts: List[Dict[str, Any]],
    batch_size: int = 8,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Agrega relevance_score, tag y flagged (moderación de contenido) a cada
    post, evaluando respecto a `query` vía LLM (por lotes, ya con reintentos
    en call_llm_json). Si un lote falla igual tras los reintentos, esos
    posts quedan con valores por defecto en vez de interrumpir el job
    completo.

    batch_size=8 (antes 15): con lotes de 15 el modelo (gemma4:e2b, chico y
    verboso) fallaba en generar JSON válido de forma consistente —no
    transitoria— en la mayoría de los lotes de jobs grandes (ver CLAUDE.md,
    testeo de max_results=30), y como la llamada usa temperature=0,
    reintentar el mismo prompt no ayudaba (mismo prompt → mismo JSON roto).
    Lotes más chicos le piden al modelo generar menos JSON por llamada,
    reduciendo la superficie de corrupción.

    Devuelve (posts, batch_errors): batch_errors lista los lotes que
    fallaron (con el motivo) para que el caller pueda avisarlo vía
    emit()/job_logs — antes esto solo quedaba en un print() a stdout,
    invisible fuera de los logs crudos del contenedor.
    """
    batch_errors: List[str] = []

    for start in range(0, len(posts), batch_size):
        batch = posts[start:start + batch_size]

        try:
            prompt = build_annotation_prompt(query, batch)
            raw_response = call_llm_json(SYSTEM_PROMPT, prompt)
            annotations = normalize_annotations(raw_response, batch_size=len(batch))
        except Exception as e:
            error_msg = f"lote {start}-{start + len(batch)}: {e}"
            print(f"[ai] error anotando {error_msg}")
            batch_errors.append(error_msg)
            annotations = {}

        for i, post in enumerate(batch):
            annotation = annotations.get(i)
            if annotation:
                post["relevance_score"] = annotation["relevance_score"]
                post["tag"] = annotation["tag"]
                post["flagged"] = annotation["flagged"]
            else:
                post.setdefault("relevance_score", None)
                post.setdefault("tag", DEFAULT_TAG)
                post.setdefault("flagged", False)

    return posts, batch_errors
