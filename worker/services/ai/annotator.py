from typing import Any, Dict, List

from .llm_client import call_llm_json
from .prompt_builder import SYSTEM_PROMPT, build_annotation_prompt
from .response_parser import DEFAULT_TAG, normalize_annotations


def annotate_posts(
    query: str,
    posts: List[Dict[str, Any]],
    batch_size: int = 15,
) -> List[Dict[str, Any]]:
    """
    Agrega relevance_score y tag a cada post, evaluando relevancia respecto
    a `query` vía LLM (por lotes). Si un lote falla, esos posts quedan con
    valores por defecto en vez de interrumpir el job completo.
    """
    for start in range(0, len(posts), batch_size):
        batch = posts[start:start + batch_size]

        try:
            prompt = build_annotation_prompt(query, batch)
            raw_response = call_llm_json(SYSTEM_PROMPT, prompt)
            annotations = normalize_annotations(raw_response, batch_size=len(batch))
        except Exception as e:
            print(f"[ai] error anotando lote {start}-{start + len(batch)}: {e}")
            annotations = {}

        for i, post in enumerate(batch):
            annotation = annotations.get(i)
            if annotation:
                post["relevance_score"] = annotation["relevance_score"]
                post["tag"] = annotation["tag"]
            else:
                post.setdefault("relevance_score", None)
                post.setdefault("tag", DEFAULT_TAG)

    return posts
