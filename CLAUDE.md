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

## Resumen ejecutivo (2026-09-28)

**Arquitectura:** FastAPI (`api`) + worker Python + Redis (cola/caché en caliente,
TTL 600s) + Postgres (historial de búsquedas y logs estructurados, vía SQLAlchemy)
+ frontend Vite/React, orquestado con Docker Compose.

**Hito 1 (2026-09-28):** todo el trabajo descrito aquí quedó integrado en
`main` (fast-forward desde `feature/source-adapters`) — es la versión que el
usuario definió como hito 1 de la plataforma. Las ramas de trabajo nuevas
deberían salir de `main`.

**Historia de ramas:** `feature/source-adapters` (creada desde `feature/db-search-history-logging`,
para no perder la persistencia en Postgres). Implementa la Fase 1 de
`INSTRUCCIONES_IA.md` (contratos internos de adaptadores por fuente) y ya
avanzó a la Fase 2 (fuentes públicas adicionales vía adaptadores: GitHub
Issues, Hacker News, RSS/Atom y CrossRef, ver más abajo — de la Fase 2
(sección 5) todavía faltan Web/Jina Reader y V2EX público, en ese orden);
`feature/db-search-history-logging` a su vez viene de
`feature/elsevier-scopus-sciencedirect`, que no tenía commits propios (idéntica
a `main`). Todas quedaron integradas en `main` con el hito 1.

### Lo que funciona hoy
- Pipeline de 4 etapas end-to-end vía SSE (`/search`, `/events`, `/job_result`)
  con scraping funcional de **StackOverflow, GitHub Issues, Hacker News,
  RSS/Atom (noticias vía Google News) y CrossRef** (cinco fuentes activas).
  El frontend ya no deja elegir fuente — cada búsqueda manda todas las
  implementadas y un planificador de IA (HU-06) decide, tras un sondeo
  rápido, cuáles consultar a fondo y con qué cupo (ver "Rendimiento y uso
  de IA").
- **CrossRef (adaptador nuevo, 2026-09-19):** `CrossRefAdapter` envuelve
  `worker/services/crossref_scraper/crossref_scraper_service.py`, que pega
  contra la API pública de búsqueda de CrossRef (`api.crossref.org/works`,
  literatura académica) con query de texto libre real, gratuita y sin
  autenticación. Implementado como prioridad para el debut (ver "Testeo
  contra los tracks del debut" más abajo): a diferencia de
  StackOverflow/GitHub/HN (búsqueda literal por palabras clave), CrossRef sí
  entiende texto libre — incluye título, autor(es) (primer autor + "et al."
  si hay más), fecha (`date-parts` → `YYYY-MM-DD`/`YYYY-MM`/`YYYY` según lo
  que venga), abstract (XML JATS, se limpia con BeautifulSoup igual que RSS)
  y hasta 5 `subject` como tags (campo semi-deprecado en CrossRef — muchos
  items no lo traen, así que igual que HN/RSS puede aportar `tags: []`, no
  rompe nada). Reutiliza `beautifulsoup4`, ya en `worker/requirements.txt` —
  no se agregó ninguna dependencia nueva. Registrado en `SOURCE_REGISTRY`,
  sumado a `PROVIDERS` en `db/seed.py` (slug `crossref`, `status="active"`)
  y a la constante `SOURCES` del frontend. **Verificado end-to-end contra
  Docker real**, incluyendo una corrida contra los 5 tracks completos del
  debut (5 fuentes, `max_results=16`, ver "Testeo contra los tracks del
  debut" — **hueco cerrado**, y ver también "`max_results` es un total...
  y lo elige la IA, no el scraper" más abajo: la primera corrida de esta
  prueba destapó un bug de reparto de cupo preexistente, ya corregido).
  Con el bug corregido, los 5 tracks llegan a 16/16 resultados, con
  StackOverflow/HN en 0 y RSS/CrossRef/GitHub repartiéndose el resto según
  relevancia real (no en partes iguales) — confirmado leyendo los títulos
  del resultado completo, no solo el conteo. También probado: CrossRef en
  solitario (10/10 resultados relevantes para "cuidados y economía del
  cuidado") y junto a una fuente inexistente en
  `sources` (no cancela el job, sigue con CrossRef).
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
- **`max_results` es un total, no un total por fuente, y lo elige la IA, no
  el scraper (corregido 2026-09-19):** la primera versión de esto (commit
  `908cfc2`) repartía `max_results` en partes iguales entre las fuentes
  activas (`per_source_limit = ceil(max_results / n_fuentes)`) — con 5
  fuentes y `max_results=16` eso le daba el mismo cupo (4) a una fuente que
  no traía nada (StackOverflow/HN) que a una fuerte (CrossRef/RSS), y
  además capaba el pool que llegaba a la IA por debajo de `max_results`
  aunque una sola fuente hubiera podido cubrirlo entera — la IA terminaba
  rankeando dentro de un pool ya recortado en partes iguales, no eligiendo
  libremente. Se detectó repitiendo el testeo de los 5 tracks del debut con
  CrossRef ya integrado (ver "Testeo contra los tracks del debut"): los
  resultados por fuente salían en múltiplos redondos de 4, señal de que no
  era la IA decidiendo. **Fix:** `per_source_limit = min(max_results,
  PER_SOURCE_CAP)` (`PER_SOURCE_CAP = 30` en `worker/main.py`) — cada fuente
  puede aportar hasta ese tope fijo, independiente de cuántas fuentes estén
  activas, y recién después `annotate_posts` (IA) asigna `relevance_score` y
  se ordena/corta a `max_results`. Reverificado con los 5 tracks: los 5
  llegaron a 16/16 (antes 9-12) y la distribución por fuente dejó de ser
  pareja (ej. RSS 13-15/16 en la mayoría, pero CrossRef 8/16 en el track de
  accesibilidad) — ahora sí es la IA priorizando por relevancia real, no el
  scraper repartiendo cupo.
- **Relevancia y etiquetado por IA real**: `annotate_posts` llama al LLM
  (gateway UNAB, `gemma4:e2b`) por lotes (`batch_size=8`) y asigna
  `relevance_score`, `tag` y `flagged` (moderación de contenido inapropiado)
  a cada post.
- **Clasificación con `max_results` grandes (30+) — bug de confiabilidad
  detectado y corregido (2026-09-19):** el usuario reportó un "error en el
  scraper" al buscar con `max_results=30`; investigando se confirmó que el
  problema real está en **classifying**, no en scraping: con el fix de
  `per_source_limit` (arriba) `max_results=30` escala el pool a clasificar
  a ~90 posts. Con el `batch_size` original (15) y el campo `justification`
  que el prompt le pedía al LLM por cada post (nunca usado — se parseaba en
  `response_parser.py` pero no se copiaba al post final), el modelo
  (`gemma4:e2b`, chico y verboso — internamente rutea a `gemma4:26b`)
  fallaba en generar JSON válido en la mayoría de los lotes de un job
  grande (5 de 6 lotes en una prueba real). Como `chat_completion` usa
  `temperature=0`, agregar reintentos solos no alcanzaba: mismo prompt →
  mismo JSON roto determinísticamente, no es una falla transitoria de red.
  **Fix de dos partes:**
  1. `llm_client.call_llm_json` ahora reintenta hasta 3 veces con backoff
     exponencial (mismo patrón que los scrapers) — sí ayuda contra fallas
     de red genuinamente transitorias (ej. el 504 de Cloudflare que se vio
     contra `quotas.devhub.cl`).
  2. Se sacó `justification` del prompt/schema (`prompt_builder.py`,
     `response_parser.py` — campo muerto) y se bajó `batch_size` de 15 a 8
     (`annotator.py`) para reducir cuánto JSON tiene que generar el modelo
     por llamada.
  Reverificado con `max_results=30` tras el fix: **0 de 12 lotes fallaron**
  (antes 5 de 6), los 30 posts finales quedaron con `relevance_score` real
  de la IA (ninguno en `None`/default), en tiempo total similar al de antes
  (~8 min) pese al doble de lotes.
  **Visibilidad (antes invisible):** `annotate_posts` ahora devuelve
  `(posts, batch_errors)` en vez de solo `posts` — si algún lote falla
  igual tras los reintentos, `worker/main.py` lo emite como evento
  `classifying` (visible en `job_logs` y por SSE al frontend) en vez de
  quedar solo en un `print()` a stdout que solo se ve con
  `docker compose logs worker`.
- **Grafo semántico (backend, fuera de la UI desde 2026-09-28)**:
  `infer_topic_relations` le pide al LLM las relaciones entre los tags más
  frecuentes; si el LLM falla, cae a un grafo de co-ocurrencia (temas que
  aparecen juntos en el mismo post) como fallback, nunca a reglas fijas. El
  usuario lo sacó de la vista principal porque no cumplía sus expectativas:
  el frontend manda `include_graph: false` y el worker ahora respeta ese
  flag (antes lo ignoraba) y no llama a `build_graph` — ahorra una llamada
  al LLM por búsqueda (`graph: null` en el resultado). `GraphView.tsx` sigue
  en el repo sin usar.
- **El pipeline es resiliente a fallas del LLM (verificado)**: si el gateway
  responde error (ej. API key inválida/revocada, 401), tanto `annotate_posts`
  como `infer_topic_relations` atrapan la excepción (después de los 3
  reintentos de `call_llm_json`, ver arriba), la imprimen (`[ai] error
  ...`) y siguen con fallback (relevancia/tag por defecto, "Sin clasificar",
  grafo por co-ocurrencia) en vez de propagarla. Las fallas de
  `annotate_posts` además quedan visibles en `job_logs`/SSE (ver arriba);
  las de `infer_topic_relations` (grafo) por ahora siguen solo en el
  `print()`, sin cambios en esta sesión. El job igual termina en
  `search_queries.status = "done"` — una falla del LLM por sí sola **no**
  genera un registro `status="error"` ni una fila `level="ERROR"` en
  `job_logs`. Solo fallas más duras (scraper, parseo del payload, etc.) que
  se escapan del `try/except` de `worker_loop()` producen ese camino de
  error. Confirmado probando ambos casos manualmente: key inválida → job
  `done` con datos degradados; payload corrupto inyectado directo en Redis →
  job `error` con `error_message` y log `level=ERROR` en `job_logs`.
- Deduplicación de posts por URL en `worker/main.py`.
- Frontend con tabla de resultados y nube de palabras (ponderada por
  `relevance_score`), con estilos de marca UNAB aplicados. **Sin selector de
  cantidad** (2026-09-28): se eliminó el slider "Máx. resultados"; cada
  búsqueda pide `MAX_RESULTS = 10` (constante en `App.tsx`), y el default de
  `max_results` en la API y el worker también bajó de 30 a 10. **Sin
  selector de fuentes**: se eliminó el checkbox manual (`AVAILABLE_SOURCES`/
  `SOURCE_ICONS` en `App.tsx`) — el frontend siempre manda todas las fuentes
  implementadas (constante `SOURCES` en `App.tsx`, hoy `["stackoverflow",
  "github", "hackernews", "rss", "crossref"]`) en cada búsqueda. Al agregar
  un adaptador nuevo hay que sumarlo también a esa constante para que se
  consulte automáticamente.
- **Historial de búsquedas y logging estructurado en Postgres** (paquete
  `db/`, rama `feature/db-search-history-logging`): `POST /search` crea una
  fila en `search_queries` (query, sources, max_results, status="queued")
  **antes** de encolar el job en Redis (`r.rpush`) — se movió el insert
  antes del `rpush` (ver "Bug de orden de escritura corregido" más abajo);
  el `worker` la actualiza a "running" al empezar, y a "done"/"error" al
  terminar (con `summary`, `posts_count`, `error_message`, `completed_at`).
  Cada llamada a `emit()` en el worker también persiste una fila en
  `job_logs` (stage, level, message, data) — reemplaza el logging por
  `print()` sueltos. Todo esto es best-effort: si Postgres falla, el
  pipeline Redis/SSE (la vía crítica) sigue funcionando igual, solo se
  pierde ese registro puntual y se imprime un warning. Probado end-to-end
  contra Postgres real.
- **HU-05 — historial/proveedores expuestos por API y frontend
  (2026-09-21, hueco cerrado):** tres endpoints nuevos de solo lectura en
  `api/main.py`, todos probados contra Docker real con datos reales:
  - `GET /providers` — catálogo completo de `search_providers` (7 fuentes,
    slug/estado/descripción/rate limit/requiere auth).
  - `GET /search_history?limit=&offset=` — historial paginado de
    `search_queries`, ordenado por `created_at desc` (`limit` acotado a
    100). Devuelve `{total, limit, offset, items}`.
  - `GET /search_history/{job_id}/logs` — logs de `job_logs` para un job
    puntual, orden cronológico; `404` si el `job_id` no existe.
  En el frontend, `App.tsx` suma un toggle "Buscar"/"Historial" en el
  navbar (estado `view`, sin afectar el flujo de búsqueda existente) y un
  componente nuevo `frontend/src/components/HistoryPanel.tsx` que consume
  los tres endpoints: tabla de fuentes registradas, tabla de historial de
  búsquedas, y un botón "Ver logs" por fila que expande los `job_logs` de
  ese job (carga perezosa, solo al expandir). Verificado visualmente por
  el usuario contra Docker real (captura de pantalla), datos reales de 49
  búsquedas históricas y 7 proveedores.
- **Bug de orden de escritura corregido (2026-09-21):** en `POST /search`
  (`api/main.py`), el insert de `SearchQuery` en Postgres ahora ocurre
  **antes** de `r.rpush("jobs:queue", job_id)`, no después. Antes el
  worker podía desencolar el job y llamar a `emit()` (que escribe en
  `job_logs`, con FK a `search_queries`) antes de que esa fila existiera,
  disparando un `ForeignKeyViolation` best-effort en los primeros eventos
  de cada job. Reverificado disparando una búsqueda real: el primer log
  ("Inicializando búsqueda...") queda registrado desde el arranque, sin
  errores de FK en los logs del worker.

> Nota: `Tareas_Pendientes.csv` (snapshot de un audit anterior) todavía marca
> el score de relevancia y el grafo como "simulados"/"Falta". Eso quedó
> desactualizado con los commits `0272c7c`, `82ca4db` y `286c1b6` — ambos ya
> usan el LLM real. Igual el bug de import bloqueante (`stackoverflowscraper`
> vs `stackoverflow_scraper`) ya está corregido. Si vas a usar ese CSV como
> fuente de verdad, primero verifica contra el código.

### Lo que está a medias o pendiente
- No hay normalización de texto (solo dedupe por URL y limpieza de HTML).
- Sin embeddings ni vector store.
- La nube de palabras no tiene interacción (hover/click) ni filtros
  coordinados con el listado.
- El frontend en Docker es un build estático servido por nginx sin
  `Cache-Control`: tras reconstruir el contenedor el navegador puede seguir
  mostrando la versión vieja hasta un Ctrl+Shift+R. Pendiente (opcional):
  `nginx.conf` con `no-cache` para `index.html`.
- Tests mínimos: solo `worker/tests/test_source_planner.py` (planificador,
  HU-06). Los adaptadores siguen sin tests (`test/snapshot.py` es un
  script de debug, no una suite).
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
- **CrossRef (prioridad del debut, sin HU asociada en `Historias_Usuario.csv`):**
  ✅ implementado (`CrossRefAdapter`, ver "Lo que funciona hoy"). Usa la API
  pública de búsqueda de CrossRef (`api.crossref.org/works`, literatura
  académica, texto libre real, gratuita y sin autenticación).

### Testeo contra los tracks del debut (2026-09-17)
La jefa del usuario compartió los 5 tracks temáticos que se van a usar el día
del debut (impacto social: autonomía económica/laboral, cuidados, violencia y
espacios seguros, inclusión/accesibilidad, STEM/IA — no son temas de
programación). Se probó cada track como búsqueda real contra Docker
(`sources` completas, `max_results=16`), primero el pipeline completo y
después cada adaptador por separado con la query cruda para aislar la causa.
**Hallazgo:** StackOverflow y Hacker News devolvieron 0 resultados en las 5
tracks, GitHub 0-2, y solo RSS (Google News) entregó resultados consistentes
(4/4 siempre) — el resultado final quedó muy por debajo de `max_results`
(4-6 posts en vez de 16) y el grafo casi vacío (RSS no aporta `tags`). No es
un bug de esta sesión: StackOverflow/GitHub/HN usan búsqueda **literal por
palabras clave**, no semántica — confirmado probando la misma fuente con
keywords cortas (`"accessibility disability"`) en vez de la pregunta
desafío completa, lo que sí trajo 5/5/5 resultados. Conclusión: esas tres
fuentes fueron priorizadas para debugging técnico (ver HU-03/HU-04 en
`Historias_Usuario.csv`) y aportan poco a temas de impacto social sin
importar la fuente — el problema es de encaje temático, no de fase de
implementación.

**Actualización 2026-09-19 — hueco cerrado, y un bug de reparto de cupo
detectado en el camino:** con el adaptador de CrossRef implementado (ver
"Lo que funciona hoy"), se repitió la misma prueba contra los 5 tracks (5
fuentes, `max_results=16`, queries en español equivalentes a las de la
jefa del usuario). Primera corrida: CrossRef entregó 4/4 en las 5 tracks
por igual (StackOverflow/HN en 0, GitHub 1-4) y el resultado final subió de
4-6 a 9-12 posts — pero el usuario notó que esos números redondos (4/4/4)
no podían ser la IA eligiendo, y tenía razón: `per_source_limit` todavía
repartía `max_results` en partes iguales entre las fuentes activas (ver
"`max_results` es un total... y lo elige la IA, no el scraper" arriba), así
que ninguna fuente podía aportar más de 4 sin importar qué tan buena fuera,
y el pool nunca llegó a superar `max_results` para que el paso de "ordenar
y cortar" hiciera algo. Con el fix (`per_source_limit` como tope fijo por
fuente, no repartido), se repitió la prueba una tercera vez: los 5 tracks
llegaron a 16/16, con distribución no pareja y consistente con relevancia
real — RSS domina la mayoría (13-15/16), CrossRef sube a 8/16 en el track
de accesibilidad. Confirmado leyendo los títulos del resultado completo de
un track (no solo el conteo): todos temáticamente relevantes.

### Historial y observabilidad (ver `Historias_Usuario.csv`)
- **Exponer historial de búsquedas y catálogo de proveedores (HU-05):**
  ✅ implementado (2026-09-21), ver "Lo que funciona hoy". `GET /providers`,
  `GET /search_history` y `GET /search_history/{job_id}/logs` en la API, y
  el tab "Historial" en el frontend (`HistoryPanel.tsx`).

### Rendimiento y uso de IA (ver `Historias_Usuario.csv`)
- **Pre-scraping / planificación de fuentes por IA (HU-06):** ✅
  implementado (2026-09-25). Antes cada búsqueda pedía hasta 30 posts a
  **cada** fuente (~150 posts con 5 fuentes) y todos pasaban por
  `annotate_posts`, aunque en los tracks del debut StackOverflow/HN aportan
  0; un job con `max_results=30` tardaba ~8 min y el frontend lo perdía
  por el timeout SSE absoluto de 240s. Ahora:
  1. **Sondeo** (`planning`): `PROBE_SIZE=5` posts por fuente, en paralelo,
     sin IA (~1-3s).
  2. **Plan**: `plan_sources()` (`worker/services/ai/source_planner.py`)
     le pasa al LLM (`planner_model` de `config/llm_config.json`, timeout
     60s, 2 intentos) la consulta, la `description` de cada adaptador y
     los títulos del sondeo, con un presupuesto de
     `max_results * POOL_FACTOR` (1.5). `normalize_allocations()` acota la
     respuesta con reglas deterministas: 0 a fuentes sin resultados en el
     sondeo, una fuente que devolvió <5 no puede recibir más de lo que
     devolvió, tope `PER_SOURCE_CAP`, presupuesto total, y completa hasta
     `max_results` si el LLM fue mezquino. Si el LLM falla o asigna 0 a
     todo → `fallback_allocations()` (proporcional al sondeo) + aviso en
     `job_logs`/SSE. El plan se emite como evento (`data.allocations`).
  3. **Scraping** en paralelo solo de las fuentes con cupo; si el cupo
     cabe en lo que ya trajo el sondeo, la fuente no se vuelve a consultar.
  Además: `annotate_posts` emite un evento por lote (`on_batch`) y el SSE
  (`api/sse_queue.py`) corta por **inactividad** (600s sin eventos) en
  vez de por duración total. Tests unitarios en
  `worker/tests/test_source_planner.py` (16, sin gateway: `cd worker &&
  python -m unittest discover -s tests`). **Verificado contra Docker:**
  track de violencia de género, `max_results=30` → 114s (antes ~8 min),
  45 posts clasificados (antes ~90), plan RSS 23/CrossRef 22 con SO/HN/
  GitHub omitidas, 30/30 con relevancia real (90-100). Consulta técnica
  ("fastapi server sent events connection timeout", 16) → 97s, plan
  GitHub 10/CrossRef 6/StackOverflow 2, RSS/HN omitidas — el planificador
  sí cambia de fuentes según el tema. El planificador cuesta ~15-17s
  (una llamada; el modelo razona internamente, ver abajo).
  **Hallazgos del gateway** (`GET /models` y pruebas directas a
  `/chat/completions`, 2026-09-25):
  - Solo hay **un** modelo habilitado: `gemma4:26b`. `gemma4:e2b` (el de
    `config/llm_config.json`) es un alias que el gateway resuelve a 26b (la
    respuesta dice `"model":"gemma4:26b"`); cualquier otro nombre (ej.
    `gemma3:1b`, `llama3.2:3b`) devuelve 400 "El modelo habilitado ahora
    es 'gemma4:26b'". **No hay un modelo más chico para elegir** hoy.
    `qwen3.8:27b` (sugerido por el usuario) es la excepción: el gateway lo
    acepta (200) pero también lo resuelve a `gemma4:26b` — está registrado
    como nombre pero no habilitado. El texto "el modelo habilitado *ahora*"
    sugiere que el gateway tiene un solo modelo activo a la vez y que puede
    rotar; volver a consultar `GET /models` antes de asumir que qwen ya
    responde (verificar el campo `model` de la respuesta, no solo el 200).
  - El modelo razona internamente y eso **no se puede apagar**:
    `reasoning_effort: "none"`, `think: false` y
    `chat_template_kwargs.enable_thinking: false` se ignoran — ~750-860
    tokens de completion ocultos y ~7s por llamada aun con prompt mínimo.
    Implica que el costo dominante es la **cantidad de llamadas**, no su
    tamaño: optimizar = menos posts a clasificar, no otro modelo.
  - Con solo los nombres de las fuentes, el planificador le asignó 12 posts
    a Hacker News en un track donde HN real devuelve 0 — el prompt de
    planificación necesita una descripción de qué cubre cada fuente (y
    eventualmente evidencia real), no solo el nombre. Por eso el diseño
    final usa sondeo + descripción, no solo el nombre.

## Estructura del repo

```
api/       FastAPI: expone /health, /search, /events (SSE), /job_result,
           /providers, /search_history, /search_history/{job_id}/logs
worker/    Loop BRPOP sobre Redis; ejecuta el pipeline de 4 etapas
  services/adapters/                 contrato SourceAdapter + SOURCE_REGISTRY (ver "Lo que funciona hoy")
  services/stackoverflow_scraper/   scraper de StackOverflow (API pública StackExchange), envuelto por StackOverflowAdapter
  services/github_scraper/          scraper de GitHub Issues (Search API pública), envuelto por GitHubAdapter
  services/hackernews_scraper/      scraper de Hacker News (Algolia HN Search API), envuelto por HackerNewsAdapter
  services/rss_scraper/             scraper de RSS/Atom (Google News RSS search), envuelto por RSSAdapter
  services/crossref_scraper/        scraper de literatura académica (CrossRef Works API), envuelto por CrossRefAdapter
  services/ai/                      llm_client, prompt_builder, annotator, relations, response_parser, source_planner (HU-06)
  tests/                            unittest del planificador (python -m unittest discover -s tests)
db/        Paquete compartido (SQLAlchemy): modelos (search_queries, job_logs,
           search_providers) + conexión Postgres + seed de proveedores. Se
           monta por volumen en api/ y worker/ (no se duplica). Conectado
           al pipeline y expuesto por API (HU-05, ver "Lo que funciona hoy").
frontend/  Vite + React + TS; d3-cloud (nube). cytoscape/GraphView.tsx
           quedan sin usar (grafo fuera de la UI desde el hito 1).
           App.tsx tiene un toggle "Buscar"/"Historial" en el navbar;
           components/HistoryPanel.tsx consume /providers y /search_history.
config/llm_config.json   Config del gateway LLM UNAB (openai-compatible, gemma4:e2b)
test/snapshot.py         Script de debug, no es una suite de tests
Historias_Usuario.csv    Backlog de historias de usuario (HU-01..06)
Tareas_Pendientes.csv    Audit de arquitectura — desactualizado en partes, ver nota arriba
INSTRUCCIONES_IA.md      Guía de integración de adaptadores de fuentes (idea tomada de "Agent Reach")
```

## Pipeline del worker (`worker/main.py`)

0. **planning** (HU-06) — busca cada fuente de `payload.sources` en
   `SOURCE_REGISTRY` (`worker/services/adapters/registry.py`), sondea
   `PROBE_SIZE` posts de cada una en paralelo y `plan_sources()` decide el
   cupo por fuente (0 = no consultar), acotado por
   `per_source_limit = min(max_results, PER_SOURCE_CAP)` (`PER_SOURCE_CAP =
   30`) — ver "Rendimiento y uso de IA". Fuente desconocida o que falla en
   el sondeo → aviso y se omite, sin cancelar las demás (hoy
   `"stackoverflow"`, `"github"`, `"hackernews"`, `"rss"` y `"crossref"`
   registradas).
1. **scraping** — pide a cada fuente con cupo `allocations[fuente]` posts,
   en paralelo (salta las fuentes cuyo cupo ya cubre el sondeo). Posts
   normalizados de todas las fuentes se acumulan y dedupean por URL. Si la
   búsqueda completa de una fuente falla, se usan sus posts del sondeo.
2. **classifying** — `annotate_posts`: relevancia + tag + moderación vía LLM
   por lotes de 8; se descartan los posts marcados `flagged`. Después se
   ordena por `relevance_score` (desc) y se corta a `max_results` — el total
   final es `max_results`, no `max_results` por fuente.
3. **building** — `build_wordcloud` (frecuencia ponderada por
   `relevance_score`) y, solo si `payload.include_graph` es true,
   `build_graph` (relaciones vía LLM + fallback de co-ocurrencia). El
   frontend actual manda `include_graph: false`.
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

0. **HU-06 (pre-scraping por IA) — ✅ implementada (2026-09-25)**, ver
   "Rendimiento y uso de IA". Pendientes menores: (a) cuando el gateway
   habilite un modelo chico (o `qwen3.8:27b` de verdad), cambiar
   `planner_model` en `config/llm_config.json` y verificar el campo
   `model` de la respuesta; (b) el frontend todavía no muestra el plan
   (`data.allocations`) más allá del texto de estado — solo queda en
   `job_logs`/historial.
1. **Adaptador de CrossRef — ✅ implementado y verificado contra los 5 tracks
   completos del debut (2026-09-19)**, ver "Lo que funciona hoy" y "Testeo
   contra los tracks del debut" (hueco cerrado). Candidato secundario, no
   decidido: búsqueda pública de Reddit (JSON de solo lectura, sin login) para voz de
   comunidad — `INSTRUCCIONES_IA.md` sección 4.3 marca Reddit *autenticado*
   como fuente que necesita revisión explícita antes de habilitarse;
   confirmar con el usuario si el modo público sin login aplica igual antes
   de construirlo, no asumirlo. Mismo patrón que `RSSAdapter`/`CrossRefAdapter`:
   módulo scraper propio + adaptador que normaliza + alta en
   `SOURCE_REGISTRY` + fila `active` en `db/seed.py` (recordar correr
   `python -m db`) + sumarla a la constante `SOURCES` del frontend
   (`frontend/src/App.tsx`).
2. De la Fase 2 de `INSTRUCCIONES_IA.md` sección 5 todavía quedan, en el
   orden recomendado por ese documento: Web/Jina Reader (o un lector HTTP
   equivalente, con las defensas de la sección 3.5 — solo http/https,
   rechazar localhost/rangos privados/metadata cloud, timeout y tamaño
   acotados) y V2EX público.
3. **HU-05 y el bug de orden de escritura — ✅ resueltos (2026-09-21)**, ver
   "Lo que funciona hoy". Queda pendiente evaluar si conviene Alembic una
   vez el esquema de `db/` empiece a cambiar más seguido (hoy `init_db()`
   con `create_all()` alcanza).
4. Confirmar acceso institucional UNAB a Scopus/ScienceDirect antes de tocar
   HU-02 (Elsevier) — no vale la pena implementar el conector sin esa
   confirmación.
5. Si se retoma X/Twitter (HU-01), verificar primero si ya se habilitó
   billing en el X Developer Portal.
6. Antes de citar `Tareas_Pendientes.csv` como estado actual, contrastar
   contra el código — quedó desactualizado en los puntos de IA (ver nota en
   el resumen ejecutivo).
7. **Fallas de `infer_topic_relations` (grafo) siguen invisibles fuera de
   `docker compose logs worker`** — a diferencia de `annotate_posts` (ya
   corregido esta sesión, ver "Clasificación con `max_results` grandes"),
   `build_graph`/`infer_topic_relations` no tienen acceso a `job_id` para
   emitir un aviso a `job_logs`/SSE si el LLM falla. Si se prioriza, requiere
   pasar `job_id` a través de `run_llm_aggregate` → `build_graph` (o mover
   el emit al caller en `worker/main.py`, similar a como quedó
   `annotate_posts`).
