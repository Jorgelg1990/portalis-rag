# Portalis RAG — Asistente documental

Monorepo (**FastAPI + Celery + Redis + PostgreSQL/pgvector + React**) para ingesta asíncrona de PDFs/DOCX, indexado vectorial y consultas RAG con **citas verificables** y trazabilidad end-to-end.

Funciona **sin claves de API** (modo mock determinista). `docker compose up --build` levanta todo el stack.

## Arranque rápido

```bash
git clone https://github.com/Jorgelg1990/portalis-rag.git
cd portalis-rag
docker compose up --build
```

| Servicio | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API + Swagger | http://localhost:8000/docs |
| Healthcheck | http://localhost:8000/health |
| Flower (colas Celery) | http://localhost:5555 |
| PostgreSQL | localhost:5432 (`postgres`/`postgres`, db `portalis`) |
| Redis | localhost:6379 |

> La primera build descarga torch/CUDA (docling) y tarda bastante (≈30–60 min según conexión). Las siguientes builds reutilizan la caché de Docker.

## Qué hace

1. **Subida** (`POST /api/documents/upload`): valida extensión, tamaño y *magic bytes*, guarda el archivo con nombre UUID y encola la ingesta.
2. **Ingesta asíncrona** (Celery + Redis): `Docling` parsea el documento (páginas + secciones), con *fallback* a `pypdf`/`python-docx`; chunking con metadatos `document_id`, `page_number`, `section`, `chunk_index`; embeddings; persistencia en pgvector. La tarea es **idempotente** (borra los fragmentos previos antes de reinsertar) y **reintenta con backoff**.
3. **Consulta** (`POST /api/query`): embedding de la pregunta → búsqueda coseno en pgvector filtrada por `workspace_id` → *evidence gating* (similitud mínima) → generación con **LiteLLM** (Gemini primario, fallback configurable) → validación de la salida estructurada con **Pydantic AI** → respuesta con `answer`, `citations`, `confidence`, `insufficient_evidence`, `action`.
4. **Frontend React**: subida de archivos, estado de ingesta en vivo (polling 3 s), chat con citas visibles y modal para abrir el fragmento fuente completo.

## API

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/documents/upload` | Sube PDF/DOCX (`file`, `workspace_id`) y encola la ingesta |
| GET | `/api/documents/status/{id}` | Estado: `pendiente` / `procesando` / `fallido` / `listo` + `error_message` |
| GET | `/api/documents/list` | Documentos del workspace |
| GET | `/api/documents/chunks/{chunk_id}` | Fragmento completo para abrir la fuente citada |
| POST | `/api/query` | Pregunta RAG con citas y gating de evidencia |
| GET | `/health` | Healthcheck |

Modelos Pydantic estrictos en `backend/app/schemas/`. Errores consistentes: `400` (tipo/tamaño/firma inválida), `404`, `413`, `422`, `503` (cola no disponible).

## Modo sin llaves (por defecto)

`.env` ya está configurado con `LLM_PROVIDER=mock` y `EMBED_PROVIDER=mock`:

- **Embeddings mock**: *hashing bag-of-words* determinista y normalizado L2 (384 dims). Conserva similitud léxica, así que la recuperación por coseno ordena fragmentos relacionados primero (no es ruido aleatorio).
- **LLM mock**: respuesta determinista anclada a los fragmentos recuperados, con citas reales.
- **Pydantic AI**: en mock usa `TestModel`; el contrato `RAGStructuredOutput` se valida igual que en producción.

### Cambiar a proveedores reales

```bash
# .env
LLM_PROVIDER=litellm
EMBED_PROVIDER=litellm
GEMINI_API_KEY=...
LITELLM_MODEL=gemini/gemini-1.5-flash
FALLBACK_LITELLM_MODEL=gpt-4o-mini
```

No hay que tocar código de negocio: `ProviderFactory` + LiteLLM abstraen el proveedor. Si el modelo real falla (timeout, rate limit, JSON inválido) se degrada al proveedor mock en vez de romper la petición.

> Si cambias `EMBEDDING_DIM`, recrea la base de datos (`docker compose down -v`) para que la columna `vector(N)` coincida.

## Tests

```bash
# Dentro del contenedor (recomendado: incluye PostgreSQL real)
docker compose exec api pytest tests/ -v

# En local, sin Docker: los tests de integración se saltan si no hay DB
cd backend && pytest tests/ -v
```

| Test | Qué cubre |
|---|---|
| `test_chunking.py` | Chunking real: metadatos página/sección, límite de tamaño, corte por página, solapamiento |
| `test_prompt.py` | Construcción del prompt: pregunta + fragmentos, límite de fragmentos, blindaje anti prompt-injection, abstención sin contexto |
| `test_providers.py` | Embeddings deterministas y ranking léxico, LLM mock, factory |
| `test_ingest_flow.py` | Flujo completo con Celery en modo eager + PostgreSQL: parse → chunk → embed → persist → estado `listo` + **idempotencia** |
| `test_pgvector_integration.py` | PostgreSQL + pgvector reales: similitud coseno (`<=>`) ordena correctamente |

CI (`.github/workflows/ci.yml`): lint (flake8) + tests contra servicios `pgvector/pgvector:pg16` y `redis:7-alpine`, más build del frontend.

## Evaluación de recuperación

```bash
python evals/run_eval.py
```

Sube `evals/manual-aduanas.pdf`, espera a `listo`, comprueba aislamiento por workspace, lanza 6 preguntas (5 respondibles + 1 fuera de dominio) y valida keywords, citas y abstención. Detalles en `evals/README.md`.

## Diagnóstico de ingestas atascadas con Flower

1. Abre http://localhost:5555.
2. **Workers**: debe haber un `celery@...` *online*. Si está offline → `docker compose restart worker`.
3. **Tasks** → filtra `ingest_document`:
   - `ACTIVE`: ejecutándose (Docling puede tardar la primera vez: descarga modelos).
   - `RESERVED/SCHEDULED`: en cola, el worker no consume.
   - `RETRY`: fallo con backoff (reintentos 3×, delay 60 s).
   - `FAILED`: agotó reintentos; abre el traceback.
   - `SUCCESS`: completada.
4. Busca por el `task_id` devuelto en el upload.
5. `docker compose logs -f worker` para el error en claro.
6. `GET /api/documents/status/{id}` (o la UI) muestra `fallido` + `error_message`.
7. Si todo está `RESERVED` y el worker online no consume: `docker compose restart worker redis`.

La tarea es idempotente: reintentar no duplica fragmentos.

## OpenTelemetry (traza end-to-end)

| Span | Dónde | Atributos |
|---|---|---|
| `rag_query` | API `/api/query` | `query.workspace`, `query.top_k`, `query.question_length`, `fragments.retrieved`, `fragments.used`, `evidence.min_score`, `model.name`, `answer.action`, `answer.insufficient_evidence`, `latency.ms` |
| `pgvector_retrieval` | API (hijo) | `fragments.retrieved` |
| `llm_call` | API (hijo) | `model.name`, `tokens.prompt`, `tokens.completion` (estimados) |
| `ingest_document` | Worker Celery | `document.id`, `workspace.id`, `parser.name`, `blocks.count`, `chunks.count`, `embedding.provider`, `error`, `error.message` |

**Ejemplo de traza de consulta:** `POST /api/query` → span HTTP de FastAPI → `rag_query` (workspace, top_k) → `pgvector_retrieval` (4 fragmentos recuperados) → `llm_call` (modelo, tokens estimados) → cierre de `rag_query` con `answer.action=answer`, `latency.ms≈120`. En ingesta: `ingest_document` (parser, bloques, chunks, proveedor de embeddings).

**Confidencialidad:** no se registra contenido de documentos, prompts ni respuestas en spans/logs. Solo IDs, conteos, modelo, latencia, tokens estimados y scores. El `trace_id` se devuelve en la respuesta de `/api/query` para correlacionar con el collector. Para visualizar trazas: apunta `OTEL_EXPORTER_OTLP_ENDPOINT` a un collector (Jaeger/Tempo); la app funciona igual sin collector.

## Seguridad

- Validación de extensión + tamaño + *magic bytes* (`%PDF-`, `PK\x03\x04`).
- Nombre en disco = UUID (la entrada del usuario nunca llega al filesystem).
- Secretos solo por variables de entorno (`.env` versionado solo con valores mock).
- Documentos tratados como **dato no confiable**: el prompt instruye a ignorar instrucciones embebidas en los fragmentos.
- Aislamiento por `workspace_id` en listado, estado, fragmentos y recuperación (chunks y documentos).
- Citas inventadas por el LLM se descartan: solo se devuelven citas que apuntan a fragmentos realmente recuperados.

## Estructura

```
backend/
  app/api/          # endpoints (documents, query)
  app/core/         # config, db, tracing
  app/models/       # SQLAlchemy (Document, Chunk)
  app/schemas/      # Pydantic estrictos
  app/services/     # parser (docling), chunking, providers, rag_agent (Pydantic AI)
  app/workers/      # celery_app, ingest_tasks
  tests/
frontend/           # React + Vite
evals/              # corpus + questions.json + run_eval.py
infra/init-db.sql   # extensión vector
docker-compose.yml
```

## Hecho / no hecho

**Hecho:** API FastAPI con modelos estrictos, ingesta Celery+Redis con Docling (+fallback), chunking con metadatos, pgvector, tarea idempotente con reintentos y timeouts, LiteLLM con fallback, salida estructurada validada con Pydantic AI, evidence gating, aislamiento por workspace, frontend con estado en vivo y citas abribles, Flower, OpenTelemetry, tests unitarios + integración + flujo Celery, eval set ejecutable, CI, modo sin llaves.

**No hecho / limitaciones:**
- Sin autenticación ni RBAC (fuera de alcance del MVP); el aislamiento es por `workspace_id` declarado por el cliente.
- Sin reranking ni búsqueda híbrida BM25 (ver `DECISIONS.md`).
- Sin OCR propio para PDFs escaneados: Docling puede no extraer texto y la ingesta falla con `error_message` claro.
- Primera ingesta con Docling descarga modelos (lento). Se puede forzar el parser ligero con `PARSER=fallback`.
- Tokens en trazas son estimaciones (no se factura ni se cuenta exacto en mock).
- La UI no tiene tests E2E (solo build en CI).
- `docker compose` está pensado para desarrollo local (volúmenes + `--reload`), no para producción.

## Uso de IA generativa

Ver `DECISIONS.md` (sección final): qué se aceptó, qué se corrigió y qué se revisó manualmente.
