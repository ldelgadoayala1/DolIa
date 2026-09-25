"""
Planificador de fuentes (HU-06): antes del scraping completo, decide cuántos
posts pedirle a cada fuente para no descargar ni clasificar con IA posts que
no aportan (antes: PER_SOURCE_CAP posts a cada fuente, ~150 con 5 fuentes,
~19 llamadas al LLM solo para clasificar).

Flujo: el worker hace un sondeo barato (PROBE_SIZE posts por fuente, sin
IA) y le pasa los resultados a plan_sources(). El LLM propone un reparto
viendo los títulos reales del sondeo, y normalize_allocations() lo acota con
reglas deterministas que no dependen de que el modelo acierte:
  - una fuente con 0 resultados en el sondeo recibe 0;
  - una fuente que devolvió menos de PROBE_SIZE ya está agotada, no puede
    recibir más de lo que devolvió;
  - tope por fuente y presupuesto total;
  - el pool nunca queda por debajo de max_results si las fuentes alcanzan.
Si el LLM falla o reparte 0 en todo, fallback_allocations() reparte el
presupuesto en proporción a los resultados del sondeo.
"""
import math
from typing import Any, Dict, List, Optional, Tuple

from .llm_client import PLANNER_MODEL, call_llm_json
from .prompt_builder import PLANNER_SYSTEM_PROMPT, build_planning_prompt

PROBE_SIZE = 5
# El pool que ve la IA de clasificación es max_results * POOL_FACTOR: margen
# para que el ordenar-y-cortar por relevance_score elija, sin volver a los
# ~150 posts de antes.
POOL_FACTOR = 1.5
# El planificador es una sola llamada corta: si el gateway se cuelga, mejor
# caer al fallback rápido que bloquear el job (con los defaults de
# call_llm_json una llamada colgada puede tardar ~15 min).
PLANNER_TIMEOUT = 60
PLANNER_ATTEMPTS = 2
MAX_TITLE_CHARS = 150


def pool_budget(max_results: int) -> int:
    return max(max_results, math.ceil(max_results * POOL_FACTOR))


def _capacity(hits: int, per_source_cap: int, probe_size: int) -> int:
    """Cuántos posts puede aportar como máximo una fuente, según el sondeo."""
    if hits <= 0:
        return 0
    if hits < probe_size:
        return hits
    return per_source_cap


def _fill(
    alloc: Dict[str, int],
    amount: int,
    weights: Dict[str, float],
    capacity: Dict[str, int],
) -> None:
    """
    Suma `amount` posts a `alloc` (in place), en proporción a `weights`,
    sin pasar la capacidad de cada fuente. Si una fuente se llena, lo que
    sobra se reparte entre las demás.
    """
    while amount > 0:
        open_sources = [
            s for s, w in weights.items()
            if w > 0 and alloc.get(s, 0) < capacity.get(s, 0)
        ]
        if not open_sources:
            return

        total_weight = sum(weights[s] for s in open_sources)
        given = 0
        for s in open_sources:
            room = capacity[s] - alloc.get(s, 0)
            share = min(room, math.floor(amount * weights[s] / total_weight))
            alloc[s] = alloc.get(s, 0) + share
            given += share

        if given == 0:
            # Montos chicos: floor() da 0 a todas; se reparte de a 1 a las de
            # más peso.
            for s in sorted(open_sources, key=lambda s: weights[s], reverse=True):
                if given == amount:
                    break
                alloc[s] = alloc.get(s, 0) + 1
                given += 1

        amount -= given


def _parse_requested(raw: Any) -> Dict[str, int]:
    """
    Acepta {"allocations": [{"source", "posts"}]} (formato pedido) o
    variantes que el modelo suele devolver: una lista directa o un dict
    {fuente: cantidad}.
    """
    items = raw.get("allocations", raw) if isinstance(raw, dict) else raw
    requested: Dict[str, int] = {}

    if isinstance(items, dict):
        items = [{"source": k, "posts": v} for k, v in items.items()]
    if not isinstance(items, list):
        return requested

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("source") or item.get("name") or "").strip().lower()
        value = item.get("posts", item.get("count", item.get("limit", 0)))
        try:
            requested[name] = max(0, int(value))
        except (TypeError, ValueError):
            continue

    return requested


def normalize_allocations(
    raw: Any,
    probe_hits: Dict[str, int],
    max_results: int,
    per_source_cap: int,
    probe_size: int = PROBE_SIZE,
) -> Optional[Dict[str, int]]:
    """
    Convierte la respuesta del LLM en un reparto válido {fuente: posts}.
    Devuelve None si el LLM no asignó nada utilizable (el caller usa el
    fallback). Ver reglas en el docstring del módulo.
    """
    budget = pool_budget(max_results)
    capacity = {s: _capacity(h, per_source_cap, probe_size) for s, h in probe_hits.items()}
    requested = _parse_requested(raw)

    alloc = {s: min(requested.get(s.lower(), 0), capacity[s]) for s in probe_hits}
    if sum(alloc.values()) == 0:
        return None

    total = sum(alloc.values())
    if total > budget:
        preferred = dict(alloc)
        alloc = {s: math.floor(n * budget / total) for s, n in preferred.items()}
        _fill(alloc, budget - sum(alloc.values()), preferred, capacity)

    target = min(max_results, sum(capacity.values()))
    if sum(alloc.values()) < target:
        # Primero se completa con las fuentes que eligió el LLM; si no
        # alcanzan, con cualquier fuente que haya devuelto algo.
        _fill(alloc, target - sum(alloc.values()), dict(alloc), capacity)
        _fill(alloc, target - sum(alloc.values()), dict(probe_hits), capacity)

    return alloc


def fallback_allocations(
    probe_hits: Dict[str, int],
    max_results: int,
    per_source_cap: int,
    probe_size: int = PROBE_SIZE,
) -> Dict[str, int]:
    """Reparto sin LLM: presupuesto en proporción a los resultados del sondeo."""
    capacity = {s: _capacity(h, per_source_cap, probe_size) for s, h in probe_hits.items()}
    alloc = {s: 0 for s in probe_hits}
    _fill(alloc, pool_budget(max_results), dict(probe_hits), capacity)
    return alloc


def plan_sources(
    query: str,
    probes: List[Dict[str, Any]],
    max_results: int,
    per_source_cap: int,
    probe_size: int = PROBE_SIZE,
) -> Tuple[Dict[str, int], Optional[str]]:
    """
    `probes`: [{"name", "description", "posts"}] con los posts del sondeo.
    Devuelve (reparto {fuente: posts}, error). Si `error` no es None, el
    reparto viene del fallback y el caller debería avisarlo por emit().
    """
    probe_hits = {p["name"]: len(p["posts"]) for p in probes}

    if sum(probe_hits.values()) == 0:
        return {name: 0 for name in probe_hits}, None

    prompt_sources = [
        {
            "name": p["name"],
            "description": p["description"],
            "hits": len(p["posts"]),
            "probe_size": probe_size,
            "titles": [(post.get("title") or "")[:MAX_TITLE_CHARS] for post in p["posts"]],
        }
        for p in probes
    ]

    try:
        prompt = build_planning_prompt(query, prompt_sources, pool_budget(max_results), per_source_cap)
        raw_response = call_llm_json(
            PLANNER_SYSTEM_PROMPT,
            prompt,
            model=PLANNER_MODEL,
            timeout=PLANNER_TIMEOUT,
            attempts=PLANNER_ATTEMPTS,
        )
        alloc = normalize_allocations(raw_response, probe_hits, max_results, per_source_cap, probe_size)
        if alloc is None:
            raise ValueError(f"el planificador no asignó posts a ninguna fuente: {raw_response}")
        return alloc, None
    except Exception as e:
        print(f"[ai] error planificando fuentes: {e}")
        return fallback_allocations(probe_hits, max_results, per_source_cap, probe_size), str(e)
