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

## Resumen ejecutivo (2026-09-17)

**Arquitectura:** FastAPI (`api`) + worker Python + Redis (cola/caché en caliente,
TTL 600s) + Postgres (historial de búsquedas y logs estructurados, vía SQLAlchemy)
+ frontend Vite/React, orquestado con Docker Compose.

**Rama activa:** `feature/source-adapters` (creada desde `feature/db-search-history-logging`,
para no perder la persistencia en Postgres). Implementa la Fase 1 de
`INSTRUCCIONES_IA.md` (contratos internos de adaptadores por fuente) y ya
avanzó a la Fase 2 (fuentes públicas adicionales vía adaptadores: GitHub
Issues, Hacker News y RSS/Atom, ver más abajo — de la Fase 2 (sección 5)
todavía faltan Web/Jina Reader y V2EX público, en ese orden);
`feature/db-search-history-logging` a su vez viene de
`feature/elsevier-scopus-sciencedirect`, que no tenía commits propios (idéntica
a `main`). **Ninguna de estas ramas está mergeada a `main` todavía** — `main`
no tiene ni el historial en Postgres ni este archivo.

### Lo que funciona hoy
- Pipeline de 4 etapas end-to-end vía SSE (`/search`, `/events`, `/job_result`)
  con scraping funcional de **StackOverflow, GitHub Issues, Hacker News y
  RSS/Atom (noticias vía Google News)** (cuatro fuentes activas). El frontend
  ya no deja elegir fuente — cada búsqueda consulta automáticamente todas las
  implementadas (ver más abajo).
- **Registro de adaptadores de fuentes** (`worker/services/adapters/`, ver
  `INSTRUCCIONES_IA.md` sección 3.1-3.2): `worker/main.py` ya no tiene un `if
  "stackoverflow" in sources` hardcodeado — itera `payload.sources`, busca cada
  una en `SOURCE_REGISTRY` (registro explícito, sin carga dinámica por nombre)
  y llama a `adapter.search(query, limit)`. Cada adaptador normaliza sus posts
  al esquema común (`title`, `url`, `source`, `content`, `author`, `date`,
  `score`, `tags`) antes de deduplicar/clasificar. Una fuente desconocida o que
  falla (excepción capturada por fuente) no cancela el job ni las demás
  fuentes — solo se emite un aviso y se sigue. `SOURCE_REGISTRY` tiene
  `StackOverflowAdapter`, `GitHubAdapter` (este último envuelve
  `worker/services/github_scraper/github_scraper_service.py`, que pega contra
  la Search API pública de GitHub con `is:issue` para excluir pull requests;
  `GITHUB_TOKEN` es opcional, solo sube el rate limit de 10 a 30 req/min) y
  `HackerNewsAdapter` (envuelve
  `worker/services/hackernews_scraper/hackernews_scraper_service.py`, que
  pega contra la API pública de búsqueda de Algolia para HN —
  `hn.algolia.com/api/v1/search` con `tags=story` para excluir comentarios—,
  no la Firebase API oficial porque esa no soporta búsqueda por texto libre;
  sin autenticación ni rate limit documentado) y `RSSAdapter` (envuelve
  `worker/services/rss_scraper/rss_scraper_service.py`, que pega contra el
  feed público de búsqueda de Google News —
  `news.google.com/rss/search?q=...`—, no una lista curada de feeds fijos:
  este endpoint sí acepta la query de texto libre del usuario y devuelve
  RSS 2.0, así que mantiene el mismo contrato de búsqueda real que las demás
  fuentes en vez de requerir mantener/filtrar una lista de feeds a mano;
  reutiliza `beautifulsoup4`/`lxml`, ya en `worker/requirements.txt`, para
  parsear el XML — no se agregó ninguna dependencia nueva). Tanto HN como
  RSS no tienen tags temáticos como SO/GitHub, así que sus posts aportan
  `tags: []` — no rompen el grafo ni la nube (que siguen funcionando con las
  demás fuentes), simplemente no suman nodos propios al grafo cuando son la
  única fuente activa. Verificado end-to-end contra Docker real: cada fuente
  por separado, las cuatro combinadas (resultados mezclados en una sola
  tabla, criterio de aceptación de `INSTRUCCIONES_IA.md` sección 8), y el
  caso de fuente desconocida en `sources` (no cancela el job ni las fuentes
  válidas).
- **Nota sobre el seed de proveedores:** `init_db()` (llamado al arrancar
  `api`/`worker`) solo crea las tablas — `seed_providers()` (el catálogo de
  `search_providers`) **no** corre automático, hay que ejecutarlo a mano
  (`docker compose run --rm api python -m db`, ver sección "Cómo correr el
  proyecto"). Si vas a dar de alta una fuente nueva en `db/seed.py`, no vas a
  ver el cambio reflejado en la tabla hasta correr ese comando.
- **`max_results` es un total, no un total por fuente**: antes cada fuente
  activa pedía `max_results` completo (con StackOverflow + GitHub, 30 posts
  pedidos terminaban en 60 antes de cortar), y ese factor de multiplicación
  iba a crecer con cada fuente nueva. Ahora `worker/main.py` reparte
  `max_results` entre las fuentes activas al pedir (`per_source_limit`), y
  después de clasificar con IA ordena todo por `relevance_score` (desc) y
  corta a `max_results` — el resultado final siempre es como máximo
  `max_results` posts, los más relevantes según la IA. Verificado: pedido de
  30 con `["stackoverflow", "github"]` → 15+15 al scrapear, 30 en el
  resultado final.
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
  `relevance_score`) y grafo, con estilos de marca UNAB aplicados. **Sin
  selector de fuentes**: se eliminó el checkbox manual (`AVAILABLE_SOURCES`/
  `SOURCE_ICONS` en `App.tsx`) — el frontend siempre manda todas las fuentes
  implementadas (constante `SOURCES` en `App.tsx`, hoy `["stackoverflow",
  "github", "hackernews", "rss"]`) en cada búsqueda. Al agregar un adaptador
  nuevo hay que sumarlo también a esa constante para que se consulte
  automáticamente.
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
- **GitHub Issues (HU-03):** ✅ implementado (`GitHubAdapter`, ver "Lo que
  funciona hoy"). Usa la Search API pública de GitHub (10 req/min sin auth,
  30 req/min con `GITHUB_TOKEN` opcional) filtrando con `is:issue`, no el
  límite de 5000/h de la API general (esa cifra corresponde a otros
  endpoints, no a Search).
- **Hacker News (HU-04):** ✅ implementado (`HackerNewsAdapter`, ver "Lo que
  funciona hoy"). Usa la API pública de búsqueda de Algolia para HN
  (`tags=story`, sin autenticación ni límite documentado), no la Firebase API
  oficial (no soporta búsqueda por texto libre).
- **RSS/Atom (Fase 2 de `INSTRUCCIONES_IA.md`, sin HU asociada en
  `Historias_Usuario.csv`):** ✅ implementado (`RSSAdapter`, ver "Lo que
  funciona hoy"). Decisión de diseño (consultada con el usuario esta
  sesión): en vez de una lista curada de feeds + filtro local de texto, usa
  el feed de búsqueda de Google News (`news.google.com/rss/search?q=...`),
  que sí soporta query de texto libre igual que las demás fuentes.

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
  services/adapters/                 contrato SourceAdapter + SOURCE_REGISTRY (ver "Lo que funciona hoy")
  services/stackoverflow_scraper/   scraper de StackOverflow (API pública StackExchange), envuelto por StackOverflowAdapter
  services/github_scraper/          scraper de GitHub Issues (Search API pública), envuelto por GitHubAdapter
  services/hackernews_scraper/      scraper de Hacker News (Algolia HN Search API), envuelto por HackerNewsAdapter
  services/rss_scraper/             scraper de RSS/Atom (Google News RSS search), envuelto por RSSAdapter
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
INSTRUCCIONES_IA.md      Guía de integración de adaptadores de fuentes (idea tomada de "Agent Reach")
```

## Pipeline del worker (`worker/main.py`)

1. **scraping** — por cada fuente en `payload.sources`, busca el adaptador en
   `SOURCE_REGISTRY` (`worker/services/adapters/registry.py`). `max_results`
   se reparte entre las fuentes activas (`per_source_limit`, división
   redondeando hacia arriba) en vez de pedírselo completo a cada una — si no,
   el volumen total (y el trabajo de clasificación IA) crecería multiplicado
   por la cantidad de fuentes registradas en vez de mantenerse acotado a
   `max_results`. Posts normalizados de todas las fuentes se acumulan y
   dedupean por URL. Fuente desconocida o que falla → aviso y se sigue con
   las demás (hoy `"stackoverflow"`, `"github"`, `"hackernews"` y `"rss"`
   registradas).
2. **classifying** — `annotate_posts`: relevancia + tag + moderación vía LLM
   por lotes de 15; se descartan los posts marcados `flagged`. Después se
   ordena por `relevance_score` (desc) y se corta a `max_results` — el total
   final es `max_results`, no `max_results` por fuente.
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
  `search_queries`, `job_logs`, `search_providers`). `init_db()` (al arrancar
  `api`/`worker`) solo crea las tablas si no existen; **el catálogo de
  proveedores no se siembra solo** — hay que correr
  `docker compose run --rm api python -m db` a mano (crea tablas + siembra,
  es idempotente) cada vez que se edite `db/seed.py`.

Desarrollo del frontend solo (fuera de Docker): `cd frontend && npm install && npm run dev`.

## Convenciones para nuevos conectores de fuentes

Un scraper nuevo (ej. Hacker News, RSS) debe implementar el contrato
`SourceAdapter` (`worker/services/adapters/base.py`): `name`, `check()`,
`search(query, limit)` y `read(url)` (este último puede lanzar
`NotImplementedError` si la fuente no lo necesita). `search()` debe devolver
posts ya normalizados al esquema común: `title`, `url`, `source`, `content`,
`author`, `date`, `score`, `tags` (`tags` se usa para nube/grafo). El propio
scraper de bajo nivel (llamadas HTTP, parseo) puede vivir en su propio módulo
—como `stackoverflow_scraper_service.py`— y el adaptador solo lo envuelve y
normaliza su salida. Una vez implementado, se registra explícitamente en
`SOURCE_REGISTRY` (`worker/services/adapters/registry.py`) — nunca cargar
adaptadores dinámicamente a partir del nombre recibido en `payload.sources`.
Así se integra en `worker/main.py` sin tocar el pipeline de IA ni el frontend.
Ver `INSTRUCCIONES_IA.md` para las reglas de seguridad (timeouts, límites de
tamaño, no SSRF, no credenciales en logs) que aplican especialmente a
adaptadores que hacen requests HTTP a terceros.

## Para la próxima sesión

1. Implementar el siguiente adaptador de la Fase 2 de `INSTRUCCIONES_IA.md`
   sección 5 — StackOverflow, GitHub, Hacker News y RSS/Atom ya están;
   quedan, en el orden recomendado por ese documento: Web/Jina Reader (o un
   lector HTTP equivalente, con las defensas de la sección 3.5 — solo
   http/https, rechazar localhost/rangos privados/metadata cloud, timeout y
   tamaño acotados) y V2EX público. Mismo patrón que `RSSAdapter`/
   `HackerNewsAdapter`: módulo scraper propio + adaptador que normaliza +
   alta en `SOURCE_REGISTRY` + fila `active` en `db/seed.py` (recordar
   correr `python -m db`) + sumarla a la constante `SOURCES` del frontend
   (`frontend/src/App.tsx`).
2. **Bug preexistente detectado (no de esta sesión, pendiente de fix):** en
   `api/main.py` (`POST /search`), `r.rpush("jobs:queue", job_id)` ocurre
   *antes* de insertar la fila en `search_queries` (Postgres). El worker
   puede desencolar el job y llamar a `emit()` (que escribe en `job_logs`)
   antes de que esa fila exista, disparando un
   `ForeignKeyViolation` best-effort (no tumba el pipeline, pero significa
   que se pierden logs iniciales de esa corrida). Reproducido en esta sesión
   con jobs de Hacker News, GitHub y StackOverflow por igual — no es
   específico de ninguna fuente. Fix sugerido: mover el insert de
   `SearchQuery` antes del `rpush`.
3. **HU-05 — exponer historial/proveedores (rama `feature/db-search-history-logging`):**
   la persistencia ya está conectada y probada (ver "Lo que funciona hoy").
   Falta la capa de lectura: endpoints en la API (ej. `GET /search_history`,
   `GET /providers`) y la vista en el frontend. Evaluar también si conviene
   Alembic una vez el esquema empiece a cambiar más seguido (hoy
   `init_db()` con `create_all()` alcanza).
4. Confirmar acceso institucional UNAB a Scopus/ScienceDirect antes de tocar
   HU-02 (Elsevier) — no vale la pena implementar el conector sin esa
   confirmación.
5. Si se retoma X/Twitter (HU-01), verificar primero si ya se habilitó
   billing en el X Developer Portal.
6. Antes de citar `Tareas_Pendientes.csv` como estado actual, contrastar
   contra el código — quedó desactualizado en los puntos de IA (ver nota en
   el resumen ejecutivo).
