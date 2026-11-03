# Portalis RAG - Asistente Documental

Monorepo con **FastAPI + Celery + Redis + PostgreSQL/pgvector + React** para ingesta asíncrona de PDFs/DOCX, indexado vectorial y consultas RAG con citas verificables.

## Características

- **Ingesta asíncrona**: Celery + Redis, parsing con Docling/fallback, chunking con metadatos (documento, página, sección)
- **Almacenamiento vectorial**: PostgreSQL + pgvector
- **RAG con citas**: Recuperación semántica, generación con LiteLLM (abstracción de proveedores), respuestas con fragmentos citados
- **Modo sin llaves**: Proveedores mock/deterministas incluidos. Funciona sin credenciales reales
- **Trazabilidad**: OpenTelemetry (API → Celery → pgvector → LLM)
- **Observabilidad**: Flower para inspeccionar colas/tareas
- **Estados claros**: pendiente / procesando / fallido / listo
- **Gating de evidencia**: Decide respuesta/abstención/petición de aclaración
- **Aislamiento por workspace/tenant**

## Requisitos

- Docker y Docker Compose

## Levantar el proyecto (sin llaves reales)

```bash
# Clonar y entrar
cd prueba-tecnica

# Levantar todo el stack
docker compose up --build
```

Servicios:
- Frontend: http://localhost:5173
- API: http://localhost:8000/docs
- Flower (inspección colas): http://localhost:5555
- Postgres: localhost:5432
- Redis: localhost:6379

**El proyecto funciona con proveedores mock por defecto** (ver `.env`). No se necesitan claves de API.

## Cómo diagnosticar una ingesta atascada con Flower

1. Abrir http://localhost:5555 (Flower UI)
2. **Workers**: comprobar que hay al menos un worker conectado (`celery@...` online). Si aparece offline → reiniciar `docker compose restart worker`
3. **Tasks**: filtrar por nombre `ingest_document`. Revisar estados:
   - `ACTIVE` - tarea en ejecución ahora mismo
   - `RESERVED/SCHEDULED` - en cola esperando worker
   - `RETRY` - reintentando tras fallo (usa backoff)
   - `FAILED` - falló tras agotar reintentos. Revisar traceback
   - `SUCCESS` - completada
4. **Tasks por ID**: buscar por `task_id` del documento (aparece en respuesta de upload / campo `task_id`)
5. **Logs**: `docker compose logs -f worker` para ver errores en tiempo real
6. **API/Estado**: revisar `status` y `error_message` del documento via API `GET /api/documents/status/{id}` o frontend
7. **Si está colgado sin progreso**: revisar Redis/worker, reintentar subiendo de nuevo o `docker compose restart worker redis`

**Notas:** La tarea es idempotente (al reintentar borra chunks previos del documento antes de regenerarlos), usa reintentos con backoff y tiene timeouts configurados.

## Ejecutar tests

```bash
cd backend
pytest tests/ -v
```

Los tests usan proveedores mock (simulados en CI).

## Traza OpenTelemetry (end-to-end)

La aplicación instrumenta spans a lo largo del flujo con atributos útiles para diagnóstico sin exponer contenido sensible:

| Span | Dónde | Atributos clave |
|---|---|---|
| `rag_query` | API (`/api/query`) | `query.workspace`, `query.top_k`, `fragments.retrieved`, `model.name`, `latency.ms` |
| `pgvector_retrieval` | API (búsqueda vectorial) | `fragments.retrieved` |
| `llm_call` | API (generación) | `model.name`, `tokens.prompt` (estimado), `tokens.completion` (estimado) |
| `ingest_document` | Worker Celery | `document.id`, `workspace.id`, `chunks.count` |

**Principios:** No se registran el texto completo de documentos ni prompts con contenido sensible. Solo IDs, metadatos, conteos, modelo, latencia y tokens estimados. La propagación entre servicios usa el contexto de tracing; con el collector configurado se puede visualizar la traza completa API → recuperación → LLM y API → encolado + worker Celery.

*Descripción*: En un trace típico se observa el span HTTP de FastAPI, luego `rag_query` con su hijo `pgvector_retrieval` (consulta a pgvector) y `llm_call` (llamada a proveedor), con atributos de latencia/fragments/modelo. Para ingesta, `ingest_document` cubre parsing/chunking/embeddings/storage.

## Estructura

```
.
├── backend/          # FastAPI + Celery workers
├── frontend/         # React + Vite
├── evals/            # Conjunto de evaluación con documentos de ejemplo
├── docker-compose.yml
├── .env              # Config (mock por defecto)
├── README.md
├── DECISIONS.md
└── .github/workflows # CI
```

## Limitaciones conocidas

- Parsing con Docling incluido pero con fallback simple para rapidez
- Embeddings mock con dimensión 384 (suficiente para demo)
- Chunking simplificado (naive) - funcional para cumplir requisitos
- Tracing OTLP intenta enviar pero no requiere collector para funcionar
- Sin auth (fuera de scope del MVP)
- Tests mínimos pero cubren flujo básico

## Estado

- [x] API FastAPI con modelos Pydantic
- [x] Ingesta Celery + Redis + pgvector
- [x] Chunking con metadatos
- [x] RAG con citas verificables
- [x] Modo mock sin llaves
- [x] Frontend React (upload, estado, chat con citas)
- [x] Flower en docker-compose
- [x] OpenTelemetry básico
- [x] Tests mínimos
- [x] CI GitHub Actions
- [x] README + DECISIONS.md
