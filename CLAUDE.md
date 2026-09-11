# WebScrappingUNAB (DolIA) — Guía del proyecto

Prototipo que busca contenido sobre un tema (ej. "tratamientos resfriado común"),
lo enriquece con IA (relevancia, nube de palabras, grafo semántico) y lo muestra
en un dashboard web con estilos UNAB.

Este archivo es la referencia persistente del proyecto: úsalo para orientarte
al empezar una sesión nueva y actualízalo cuando el estado descrito aquí quede
desactualizado (no dejes que se pudra).

> **Regla de flujo de trabajo:** antes de hacer commit de cualquier cambio que
> implemente funcionalidad nueva o modifique el estado del proyecto (no aplica
> a commits triviales tipo typo/formato), actualizar este archivo para que
> "Resumen ejecutivo" y las secciones afectadas reflejen la realidad del
> código. Si el cambio no altera nada de lo documentado aquí, no hace falta
> tocarlo.

## Resumen ejecutivo (2026-09-11)

**Arquitectura:** FastAPI (`api`) + worker Python + Redis (cola/caché en caliente,
TTL 600s) + Postgres (historial de búsquedas y logs estructurados, vía SQLAlchemy)
+ frontend Vite/React, orquestado con Docker Compose.

**Rama activa:** `feature/db-search-history-logging` (creada desde `feature/elsevier-scopus-sciencedirect`,
que a su vez no tenía commits propios — es idéntica a `main`).

### Lo que funciona hoy
- Pipeline de 4 etapas end-to-end vía SSE (`/search`, `/events`, `/job_result`)
  con scraping funcional de **StackOverflow** (única fuente activa).
- **Relevancia y etiquetado por IA real**: `annotate_posts` llama al LLM
  (gateway UNAB, `gemma4:e2b`) por lotes y asigna `relevance_score`, `tag` y
  `flagged` (moderación de contenido inapropiado) a cada post.
- **Grafo semántico real**: `infer_topic_relations` le pide al LLM las
  relaciones entre los tags más frecuentes; si el LLM falla, cae a un grafo de
  co-ocurrencia (temas que aparecen juntos en el mismo post) como fallback,
  nunca a reglas fijas.
- **El pipeline es resiliente a fallas del LLM (verificado)**: si el gateway
  responde error (ej. API key inválida/revocada, 401), tanto `annotate_posts`
  como `infer_topic_relations` atrapan la excepción, la imprimen (`[ai] error
  ...`) y siguen con fallback (relevancia/tag por defecto, "Sin clasificar",
  grafo por co-ocurrencia) en vez de propagarla. El job igual termina en
  `search_queries.status = "done"` — una falla del LLM por sí sola **no**
  genera un registro `status="error"` ni una fila `level="ERROR"` en
  `job_logs`. Solo fallas más duras (scraper, parseo del payload, etc.) que
  se escapan del `try/except` de `worker_loop()` producen ese camino de
  error. Confirmado probando ambos casos manualmente: key inválida → job
  `done` con datos degradados; payload corrupto inyectado directo en Redis →
  job `error` con `error_message` y log `level=ERROR` en `job_logs`.
- Deduplicación de posts por URL en `worker/main.py`.
- Frontend con tabla de resultados, nube de palabras (ponderada por
  `relevance_score`) y grafo, con estilos de marca UNAB aplicados.
- **Historial de búsquedas y logging estructurado en Postgres** (paquete
  `db/`, rama `feature/db-search-history-logging`): `POST /search` crea una
  fila en `search_queries` (query, sources, max_results, status="queued")
  antes de encolar el job; el `worker` la actualiza a "running" al empezar,
  y a "done"/"error" al terminar (con `summary`, `posts_count`,
  `error_message`, `completed_at`). Cada llamada a `emit()` en el worker
  ahora también persiste una fila en `job_logs` (stage, level, message,
  data) — reemplaza el logging por `print()` sueltos. Todo esto es
  best-effort: si Postgres falla, el pipeline Redis/SSE (la vía crítica)
  sigue funcionando igual, solo se pierde ese registro puntual y se
  imprime un warning. Probado end-to-end contra Postgres real (ver
  commits de esta rama). **Falta:** exponer este historial/log por API
  (ej. `GET /search_history`, `GET /providers`) y mostrarlo en el
  frontend — todavía no hay UI ni endpoint de lectura, solo se puede
  consultar la tabla directamente.

> Nota: `Tareas_Pendientes.csv` (snapshot de un audit anterior) todavía marca
> el score de relevancia y el grafo como "simulados"/"Falta". Eso quedó
> desactualizado con los commits `0272c7c`, `82ca4db` y `286c1b6` — ambos ya
> usan el LLM real. Igual el bug de import bloqueante (`stackoverflowscraper`
> vs `stackoverflow_scraper`) ya está corregido. Si vas a usar ese CSV como
> fuente de verdad, primero verifica contra el código.

### Lo que está a medias o pendiente
- **Historial/logs en Postgres — persistencia lista, falta exposición:** ver
  detalle arriba en "Lo que funciona hoy". El catálogo de proveedores
  (`search_providers`, sembrado por `db/seed.py`) tampoco se expone todavía
  por API ni frontend — solo existe la tabla.
- No hay normalización de texto (solo dedupe por URL y limpieza de HTML).
- Sin embeddings ni vector store.
- `max_results` (slider 1-200) funciona pero sin corte/orden real por score.
- Nube de palabras y grafo no tienen interacción (hover/click) ni filtros
  coordinados con el listado — cada visualización es independiente.
- Sin tests (solo `test/snapshot.py`, un script de debug).
- Sin README de usuario final (este archivo cubre ese hueco parcialmente).

### Fuentes adicionales (ver `Historias_Usuario.csv`)
- **X/Twitter (HU-01):** implementado y revertido — bloqueado porque el X
  Developer Portal exige método de pago incluso en el tier gratuito.
  Credenciales ya están en `.env`.
- **Scopus/ScienceDirect (HU-02):** pendiente; falta confirmar acceso
  institucional UNAB a la API de Elsevier (`ELSEVIER_API_KEY` reservada en
  `.env`/`.env.example`) antes de implementar el conector. Da nombre a la
  rama actual pero aún no se ha iniciado.
- **GitHub Issues (HU-03):** priorizada para la próxima sesión — sin costo,
  rate limit generoso (5000 req/h autenticado), mismo contrato que
  `stackoverflow_scraper_service.py`. **Siguiente paso recomendado.**
- **Hacker News (HU-04):** priorizada como complemento liviano, API pública
  sin autenticación.

### Historial y observabilidad (ver `Historias_Usuario.csv`)
- **Exponer historial de búsquedas y catálogo de proveedores (HU-05):**
  priorizada para la próxima sesión. El backend ya persiste todo en Postgres
  (`search_queries`, `job_logs`, `search_providers` — ver "Lo que funciona
  hoy"); falta la capa de lectura: endpoints en la API y vista en el
  frontend. Hoy solo se consulta conectándose directo a la base.

## Estructura del repo

```
api/       FastAPI: expone /health, /search, /events (SSE), /job_result
worker/    Loop BRPOP sobre Redis; ejecuta el pipeline de 4 etapas
  services/stackoverflow_scraper/   scraper de StackOverflow (API pública StackExchange)
  services/ai/                      llm_client, prompt_builder, annotator, relations, response_parser
db/        Paquete compartido (SQLAlchemy): modelos (search_queries, job_logs,
           search_providers) + conexión Postgres + seed de proveedores. Se
           monta por volumen en api/ y worker/ (no se duplica). Ya conectado
           al pipeline (ver "Lo que funciona hoy"); falta exponerlo por API.
frontend/  Vite + React + TS; cytoscape (grafo), d3-cloud (nube)
config/llm_config.json   Config del gateway LLM UNAB (openai-compatible, gemma4:e2b)
test/snapshot.py         Script de debug, no es una suite de tests
Historias_Usuario.csv    Backlog de fuentes adicionales (HU-01..04)
Tareas_Pendientes.csv    Audit de arquitectura — desactualizado en partes, ver nota arriba
```

## Pipeline del worker (`worker/main.py`)

1. **scraping** — `extract_full_data(query, max_results)` sobre la(s) fuente(s)
   activa(s) en `payload.sources` (hoy solo `"stackoverflow"`); dedupe por URL.
2. **classifying** — `annotate_posts`: relevancia + tag + moderación vía LLM
   por lotes de 15; se descartan los posts marcados `flagged`.
3. **building** — `build_graph` (relaciones vía LLM + fallback de
   co-ocurrencia) y `build_wordcloud` (frecuencia ponderada por
   `relevance_score`).
4. **finalize** — resultado completo (`summary`, `wordcloud`, `graph`,
   `posts`) se guarda en Redis (`job:{id}:result`, TTL 600s) y se emite por SSE.

Cada etapa emite eventos de progreso (`emit(job_id, stage, progress, status)`)
que el frontend consume vía `/events`; `emit()` también persiste cada evento
como fila en `job_logs` (Postgres). Al terminar (o fallar), `search_queries`
queda con `status`, `summary`, `posts_count`/`error_message` y `completed_at`.

## Cómo correr el proyecto

```bash
cp .env.example .env   # completar LLM_API_KEY (y ELSEVIER_API_KEY si aplica)
docker compose up --build
```

- Frontend: http://localhost:8080
- API: http://localhost:8000 (docs automáticas en `/docs`)
- Redis: 6379, Postgres: 5432 (historial de búsquedas y logs — tablas
  `search_queries`, `job_logs`, `search_providers`; se crean/siembran solas
  al arrancar `api`/`worker` vía `init_db()`, o a mano con
  `docker compose run --rm api python -m db`)

Desarrollo del frontend solo (fuera de Docker): `cd frontend && npm install && npm run dev`.

## Convenciones para nuevos conectores de fuentes

Un scraper nuevo (ej. GitHub, Hacker News) debe seguir el contrato de
`stackoverflow_scraper_service.py`: exponer `extract_full_data(query, max_results)`
devolviendo `{"posts": [...], "corpus": [...]}`, donde cada post trae al menos
`title`, `url`, `source`, `score`, `date`, `author`, y opcionalmente `tags`
(se usan para nube/grafo). Así se integra en `worker/main.py` sin tocar el
pipeline de IA ni el frontend.

## Para la próxima sesión

1. **HU-05 — exponer historial/proveedores (rama `feature/db-search-history-logging`):**
   la persistencia ya está conectada y probada (ver "Lo que funciona hoy").
   Falta la capa de lectura: endpoints en la API (ej. `GET /search_history`,
   `GET /providers`) y la vista en el frontend. Evaluar también si conviene
   Alembic una vez el esquema empiece a cambiar más seguido (hoy
   `init_db()` con `create_all()` alcanza).
2. Implementar `github_scraper_service.py` (HU-03) siguiendo el contrato de
   arriba; es la fuente desbloqueada más rápida (sin billing). Al hacerlo,
   dar de alta el proveedor en `db/seed.py` (`status="active"`).
3. Confirmar acceso institucional UNAB a Scopus/ScienceDirect antes de tocar
   HU-02 (Elsevier) — no vale la pena implementar el conector sin esa
   confirmación.
4. Si se retoma X/Twitter (HU-01), verificar primero si ya se habilitó
   billing en el X Developer Portal.
5. Antes de citar `Tareas_Pendientes.csv` como estado actual, contrastar
   contra el código — quedó desactualizado en los puntos de IA (ver nota en
   el resumen ejecutivo).
