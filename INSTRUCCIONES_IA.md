# Instrucciones para trabajar con IA en DolIa

Este documento define cómo debe trabajar una IA en este repositorio y cómo
aprovechar las ideas de Agent Reach sin convertir DolIa en una copia ni en un
instalador de herramientas externas.

## 1. Objetivo del proyecto

DolIa es una aplicación web de investigación y análisis:

```text
Frontend React -> API FastAPI -> Redis -> Worker -> fuentes externas
                                      -> normalización
                                      -> análisis IA
                                      -> SSE -> Frontend
```

La primera evolución recomendada es permitir búsquedas en varias fuentes y
mostrar los resultados normalizados en la tabla, la nube de palabras y el
grafo existente.

## 2. Regla principal de integración

Agent Reach debe utilizarse como referencia conceptual y, como máximo, como
fuente de pequeños adaptadores revisados manualmente. No se debe convertir en
una dependencia ejecutada dentro de la API o del worker sin una decisión
explícita y una revisión de seguridad.

La integración debe respetar los contratos actuales de DolIa:

- La API recibe la búsqueda y crea el `job_id`.
- Redis encola el trabajo.
- El worker ejecuta las fuentes y emite eventos con `push_event`.
- El frontend consume SSE y renderiza el resultado final.
- Las fuentes deben devolver un formato común antes de pasar al análisis IA.

## 3. Qué SÍ copiar o abstraer de Agent Reach

### 3.1 Contrato de adaptadores

Copiar la idea de que cada fuente tiene una implementación independiente con
operaciones pequeñas y verificables. En DolIa se recomienda definir un
protocolo propio, por ejemplo:

```python
class SourceAdapter(Protocol):
    name: str

    def check(self) -> dict:
        ...

    def search(self, query: str, limit: int) -> list[dict]:
        ...

    def read(self, url: str) -> dict:
        ...
```

No copiar clases completas si usan dependencias, rutas de configuración o
comandos que DolIa no necesita.

### 3.2 Registro de fuentes

Copiar el patrón de registro centralizado para reemplazar condicionales
dispersos en el worker:

```python
SOURCE_REGISTRY = {
    "stackoverflow": StackOverflowAdapter(),
    "web": WebAdapter(),
    "rss": RSSAdapter(),
    "v2ex": V2EXAdapter(),
}
```

El registro debe ser explícito. No cargar módulos arbitrarios desde nombres
recibidos por el usuario.

### 3.3 Diagnóstico de capacidades

Copiar la idea de `doctor` como una función de diagnóstico que informe si una
fuente está disponible, requiere credenciales o no puede usarse en el entorno.

El diagnóstico debe ser de solo lectura:

- No instalar paquetes.
- No modificar el sistema.
- No escribir tokens.
- No importar cookies automáticamente.
- No ejecutar comandos sugeridos por una respuesta remota.

La salida debe poder mostrarse en la UI y, si es útil, exponerse mediante un
endpoint como `GET /sources`.

### 3.4 Normalización de resultados

Copiar el concepto de que cada backend devuelve datos hacia un esquema común.
El formato interno recomendado es:

```python
{
    "title": "Título",
    "url": "https://...",
    "source": "stackoverflow",
    "content": "Texto opcional",
    "author": "Autor o '-'",
    "date": "Fecha o '-'",
    "score": 0,
    "tags": [],
}
```

La normalización debe ocurrir en el worker, antes de deduplicar, clasificar,
construir la nube de palabras o generar el grafo.

### 3.5 Límites de lectura web

Copiar las defensas del canal web de Agent Reach, adaptándolas a DolIa:

- Solo aceptar `http` y `https`.
- Rechazar `localhost`, loopback, rangos privados y metadatos cloud.
- Aplicar timeout corto.
- Limitar el tamaño máximo de la respuesta.
- Detectar respuestas de CAPTCHA o bloqueo.
- No seguir redirecciones hacia destinos privados.
- Registrar dominio, estado y duración sin registrar secretos.

La lectura web debe estar en un adaptador aislado y no mezclarse con la lógica
de Redis, SSE o los componentes React.

### 3.6 Estados y progreso

Copiar la idea de etapas explícitas para el pipeline:

```text
discovering
fetching
normalizing
deduplicating
classifying
building_graph
completed
```

Cada etapa debe emitir eventos compatibles con el formato actual:

```json
{
  "type": "progress",
  "stage": "fetching",
  "progress": 35,
  "status": "Consultando fuentes...",
  "data": {"source": "web", "count": 4}
}
```

No cambiar el contrato SSE sin actualizar el frontend y sus pruebas en el
mismo cambio.

## 4. Qué NO copiar de Agent Reach

### 4.1 No copiar el instalador del sistema

No copiar ni integrar:

- `agent-reach install --system`.
- Lógica que instala paquetes del sistema.
- Lógica que instala herramientas globales con `pipx`, `npm`, `uv` o `brew`.
- Lógica que modifica `PATH`, shells o configuraciones globales.
- Scripts que clonan repositorios externos durante una búsqueda.

DolIa debe declarar sus dependencias en sus propios archivos de build y
`requirements.txt`. La ejecución de la aplicación no debe instalar software.

### 4.2 No copiar el almacenamiento de credenciales

No copiar:

- Importación automática de cookies del navegador.
- Lectura de perfiles Chrome, Firefox, Edge o Brave.
- Archivos de tokens en el HOME del usuario.
- Sincronización de credenciales legacy.
- Variables secretas incluidas en eventos SSE, logs o resultados.

Si una fuente necesita autenticación, primero debe existir un diseño explícito
de secretos para DolIa. Nunca se debe montar el HOME del host en un contenedor.

### 4.3 No copiar canales que requieran sesión sin autorización

No habilitar automáticamente Twitter/X, Reddit autenticado, Facebook,
Instagram, Xiaohongshu, Xueqiu, Boss o LinkedIn con browser automation. Esas
fuentes requieren revisión específica, consentimiento del usuario y pruebas de
aislamiento.

La primera fase debe limitarse a fuentes públicas y sin credenciales:

- StackOverflow.
- Web mediante un lector HTTP controlado.
- RSS/Atom.
- V2EX público.

### 4.4 No copiar la interfaz CLI como interfaz principal

El CLI de Agent Reach es útil para diagnóstico, pero DolIa es una aplicación
web. No reemplazar el frontend por comandos de terminal ni hacer que la API
invoque el CLI como subproceso para cada búsqueda.

### 4.5 No copiar dependencias innecesarias

No añadir todo `agent-reach[all]`, Playwright, navegadores, Node, `gh`,
`mcporter` o herramientas de scraping solo para habilitar una fuente. Cada
fuente debe justificar sus dependencias y tener un adaptador independiente.

## 5. Orden recomendado de implementación

### Fase 0: línea base

1. Levantar DolIa con Docker Compose.
2. Verificar `/health`.
3. Ejecutar una búsqueda StackOverflow existente.
4. Confirmar que el frontend recibe eventos SSE y muestra resultados.
5. Guardar el comportamiento actual antes de refactorizar.

### Fase 1: contratos internos

1. Crear el módulo de adaptadores en el worker.
2. Definir el esquema normalizado.
3. Crear el registro de fuentes.
4. Adaptar StackOverflow al nuevo contrato.
5. Mantener el resultado actual del frontend sin cambios visuales.

### Fase 2: fuentes públicas adicionales

Implementar una fuente por cambio, en este orden:

1. Web/Jina Reader o lector HTTP equivalente.
2. RSS/Atom.
3. V2EX público.

Cada adaptador debe incluir pruebas unitarias de respuestas válidas, vacías,
malformadas, timeouts y errores HTTP.

### Fase 3: diagnóstico en la UI

1. Añadir `GET /sources` o equivalente.
2. Mostrar estado, nombre y motivo de disponibilidad.
3. Permitir seleccionar solo fuentes disponibles.
4. No mostrar una fuente como funcional si requiere credenciales ausentes.

### Fase 4: seguridad y operación

1. Quitar exposición innecesaria de Redis y PostgreSQL al host.
2. Mover contraseñas a variables de entorno o secretos de Docker.
3. Restringir CORS a los orígenes reales del frontend.
4. Aplicar límites de CPU, memoria, procesos y filesystem al worker.
5. Aplicar allowlist de dominios si el modo web se usa en producción.
6. Añadir trazabilidad sin almacenar contenido sensible innecesario.

## 6. Reglas de seguridad obligatorias

- No hacer `git clone` de repositorios externos durante una petición.
- No ejecutar shell con `shell=True` para datos controlados por el usuario.
- No construir comandos concatenando consultas, URLs o nombres de fuentes.
- No aceptar rutas locales como URL de lectura.
- No permitir SSRF contra servicios internos, Redis, PostgreSQL o metadata cloud.
- No registrar `LLM_API_KEY`, cookies, tokens, cabeceras `Authorization` ni URLs
  con credenciales.
- Aplicar límites de longitud a consultas, URLs, títulos y contenido extraído.
- Usar timeouts en toda llamada HTTP y de Redis.
- Mantener el worker separado de la API y sin privilegios root.

## 7. Reglas de trabajo para la IA

Antes de editar:

1. Leer el módulo propietario del comportamiento.
2. Leer una prueba cercana o crear una prueba mínima.
3. Formular una hipótesis concreta sobre el cambio.
4. Hacer el cambio más pequeño que permita comprobarla.

Después de editar:

1. Ejecutar primero la prueba relacionada con el cambio.
2. Ejecutar el build o typecheck del componente afectado.
3. Ejecutar la suite completa si el cambio cruza API, worker y frontend.
4. Revisar `git diff --check`.
5. No corregir fallos no relacionados.

No modificar archivos generados, `node_modules`, artefactos de Docker o datos
de usuario salvo que sea imprescindible y esté documentado.

## 8. Criterios de aceptación del primer MVP

La integración se considera lista cuando:

- Una consulta puede usar al menos dos fuentes públicas.
- Los resultados de ambas fuentes aparecen en la misma tabla.
- Los duplicados se eliminan por URL normalizada.
- Cada resultado conserva su fuente de origen.
- El progreso SSE identifica la fuente y la etapa activa.
- Un timeout de una fuente no cancela las demás.
- Una fuente caída produce un aviso comprensible y no un error 500 global.
- El grafo y la nube de palabras siguen funcionando con el formato normalizado.
- No se requieren cookies, tokens de usuario ni instalaciones durante la ejecución.
- Las pruebas cubren éxito, vacío, timeout, error HTTP y contenido malformado.

## 9. Comandos de validación

Desde la raíz de DolIa:

```bash
docker compose config
docker compose build
docker compose up -d
curl http://localhost:8000/health
docker compose logs --tail=100 api worker
```

Antes de aceptar cambios en Python:

```bash
python -m compileall api worker
```

Antes de aceptar cambios en frontend:

```bash
cd frontend
npm run build
```

La suite completa de pruebas debe ejecutarse cuando exista una suite ampliada.
No considerar una demo manual como sustituto de pruebas de seguridad o de
contrato.

## 10. Decisión de diseño resumida

DolIa debe adoptar de Agent Reach sus ideas de adaptadores, registro,
diagnóstico, normalización, límites HTTP y estados de progreso. Debe rechazar
su superficie de instalación global, manejo de cookies, automatización de
navegadores, ejecución de herramientas externas y cualquier acceso implícito a
credenciales.

La regla práctica es:

> Copiar contratos y controles; no copiar privilegios, instaladores ni
> credenciales.