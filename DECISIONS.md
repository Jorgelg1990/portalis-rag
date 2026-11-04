# DECISIONS.md

Decisiones de diseño, alternativas descartadas y el porqué. Los números de la sección 1 salen de `evals/run_eval.py`.

## 1. Chunking y recuperación

**Estrategia**

- **Parsing**: Docling como parser principal (`PARSER=docling`), que aporta estructura (bloques, páginas, encabezados de sección). *Fallback* automático a `pypdf` (PDF) y `python-docx` (DOCX) si Docling no está disponible, falla o no extrae texto. El fallo nunca se silencia: si ningún parser obtiene texto, la tarea termina en `fallido` con `error_message`.
- **Chunking** (`backend/app/services/chunking.py`): agrupación de bloques en fragmentos de ≤ 800 caracteres (`CHUNK_MAX_CHARS`).
  - **Un chunk nunca cruza dos páginas**: la cita `documento + página` debe ser exacta.
  - **Se propaga la sección** del último encabezado visto (Docling/Heading de DOCX).
  - Bloques mayores que el límite se parten por frases con **solapamiento de 120 caracteres**, para no perder la frontera.
  - Se guarda `chunk_index` para reconstruir el orden.
- **Recuperación**: similitud coseno en pgvector (`embedding <=> query`) con `top_k` 1–10 (4 por defecto), filtrada por `workspace_id` y por documentos en estado `listo`.
- **Sin reranking ni búsqueda híbrida**: el corpus del MVP es pequeño y estructurado; añadir BM25 + cross-encoder multiplica latencia y dependencias sin ganancia medible aquí.

**Justificación con la evaluación**

`evals/` contiene un PDF de 2 páginas generado de forma reproducible (`generate_sample.py`), 5 preguntas respondibles y 1 fuera de dominio. `run_eval.py` valida: recuperación (keywords en respuesta/citas), citabilidad (cada cita apunta a un chunk recuperado), gating (abstención fuera de dominio) y aislamiento por workspace.

- Con embeddings mock (hashing léxico) la recuperación acierta en las 5 preguntas y se abstiene en la fuera de dominio. Es una prueba del **pipeline**, no del techo semántico de un modelo real.
- Los embeddings mock **no son ruido aleatorio**: son bolsas de palabras con hash y normalización L2, de modo que la similitud coseno conserva relación léxica. Eso permite que el eval tenga sentido sin claves.
- **Limitación honesta**: sin embeddings reales no se recuperan paráfrasis sin solape léxico. Con Gemini/`text-embedding-004` se espera mejor recall; el umbral `MIN_EVIDENCE_SCORE=0.12` está calibrado para los mock y **debe recalibrarse** al cambiar de proveedor.

## 2. Poca evidencia, contradicciones y UX

**Comportamiento**

1. **Sin fragmentos** (`fragments_retrieved = 0`): `action=abstain`, `insufficient_evidence=true`, `confidence=0`, mensaje que pide reformular o subir el documento.
2. **Fragmentos recuperados pero por debajo del umbral** (`score < MIN_EVIDENCE_SCORE`): mismo comportamiento (`model_used=evidence-gate`). Esto evita el fallo típico de "siempre hay algo en el top-k".
3. **Evidencia suficiente**: se responde con citas. Las citas que el modelo invente se **descartan** en el backend si su `chunk_id` no está entre los fragmentos recuperados.
4. **Contradicciones**: no se resuelven automáticamente. Si dos fragmentos discrepan, ambos pueden aparecer como citas y el usuario decide. El sistema no elige una versión sin decirlo.

**UX**

- Citas siempre visibles con documento, página, sección y score de similitud.
- Botón por cita que abre el **fragmento fuente completo** (`GET /api/documents/chunks/{id}`), no solo el snippet.
- Badge de metadatos: confianza, acción, nº de fragmentos, latencia y modelo.
- Abstención redactada como acción útil ("reformula o sube el documento"), no como error.
- Estado de ingesta visible por documento y `error_message` cuando falla.

**Por qué**: en un asistente documental, una respuesta inventada cuesta más que una abstención. Transparencia > falsa certeza.

## 3. Política de proveedor y coste

- **Primario**: Gemini Flash vía LiteLLM (`LITELLM_MODEL=gemini/gemini-1.5-flash`): buena relación calidad/precio/latencia para RAG extractivo.
- **Fallback**: segundo modelo (`FALLBACK_LITELLM_MODEL`, por defecto `gpt-4o-mini`) y, como última red, el proveedor mock determinista. Se activa ante error de API, timeout (30 s), rate limit o JSON que no valida el esquema.
- **Sin claves**: `LLM_PROVIDER=mock` / `EMBED_PROVIDER=mock` por defecto. CI y demo funcionan sin credenciales.
- **Control de coste**: `top_k` acotado (≤10), contexto limitado a 4 fragmentos × 600 caracteres, `temperature=0`, prompt acotado y una sola llamada por consulta (sin agentes multi-turno).
- **Observabilidad de coste**: cada respuesta incluye `model_used` y `latency_ms`; el span `llm_call` registra tokens estimados. Con LiteLLM real se puede sustituir la estimación por el `usage` del proveedor.
- **Trade-offs aceptados**:
  - Flash en vez de Pro: menos calidad en preguntas de razonamiento, mucho menor coste/latencia.
  - Fallback a mock: mantiene disponibilidad, pero la respuesta degradada es extractiva y hay que señalarla (`model_used`).
  - Una sola llamada: sin auto-crítica ni reintentos de calidad; el gating y la validación cubren el riesgo principal.
- **Abstracción**: `ProviderFactory` + LiteLLM permiten cambiar de proveedor sin tocar endpoints, chunking ni gating.

## 4. Trazas, logs y métricas vs confidencialidad

**Se registra**

- IDs (`document_id`, `chunk_id`, `task_id`, `trace_id`, `workspace_id`).
- Metadatos: nombre de archivo, tipo, tamaño, página, sección.
- Métricas: latencia, nº de fragmentos recuperados/usados, score mínimo, modelo, tokens estimados, nº de chunks/bloques.
- Errores acotados (`tipo: mensaje` truncado a 500 caracteres).

**No se registra**

- Contenido de documentos, prompts completos ni respuestas.
- Secretos o claves (solo variables de entorno).
- Texto libre de fragmentos en spans o logs.

**Por qué**: permite diagnosticar "ingesta lenta", "recuperación mala" o "proveedor caído" con conteos y latencias, sin convertir el sistema de trazas en una copia del corpus. El contenido solo se muestra al usuario final como cita (requisito de producto) y se sirve bajo demanda por workspace.

**Implementación**: atributos numéricos/IDs en spans; `trace_id` devuelto por `/api/query`; sin `span.add_event` con contenido. La app funciona sin collector OTLP.

## 5. Salida estructurada con Pydantic AI

- `backend/app/services/rag_agent.py` define `RAGStructuredOutput` (`answer`, `citations[]`, `confidence` 0–1, `insufficient_evidence`, `action`) y un `Agent` de Pydantic AI con `result_type=RAGStructuredOutput`.
- **Mock**: `TestModel` (sin claves). El contenido de `TestModel` no es semántico, así que se sustituye por una respuesta determinista anclada a los fragmentos reales y **se revalida con el mismo modelo Pydantic**.
- **Real**: `FunctionModel` envuelve la llamada a LiteLLM, de modo que el proveedor sigue siendo intercambiable y el JSON se valida contra el esquema. Si esa ruta falla, se valida el JSON de LiteLLM directamente con el mismo modelo; nunca se devuelve dato sin validar.
- Cualquier fallo acaba en abstención controlada, no en un 500.
- Se descartó la vía "alternativa justificada" (solo Pydantic `model_validate`): el requisito pedía explícitamente Pydantic AI.

## 6. Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Base vectorial dedicada (Qdrant/Weaviate) | pgvector cubre el volumen y reduce servicios a operar |
| Reranker cross-encoder | Latencia y dependencias; sin corpus grande que lo justifique |
| Híbrido BM25 + vectorial | Complejidad de dos índices; el eval no muestra fallos de recall léxico |
| Chunking semántico por embeddings | Coste de embeddings por frase y más complejidad; el corte por bloques/página es suficiente |
| `langchain` para todo el pipeline | Capa extra sobre piezas que ya controlamos; solo se usa `langchain-text-splitters` como dependencia de docling |
| Streaming token a token | El contrato es JSON estructurado; el streaming complica la validación |
| Autenticación completa | Fuera del alcance del MVP; se declara como limitación |

## 7. Uso de IA generativa

**Aceptado (y revisado)**

- Scaffolding del monorepo, `docker-compose`, componentes React, esquemas Pydantic y esqueletos de tests.

**Corregido durante la revisión**

- `litellm==1.52.3` no existe → `1.56.8`; conflicto `pydantic` ↔ `pydantic-ai` → `pydantic==2.10.6`.
- Embeddings mock de 384 dims reales (antes generaba 192) y sustituidos por hashing léxico normalizado.
- Enum de estado con `values_callable` para guardar `pendiente/procesando/...` en minúsculas.
- `CAST(:query_emb AS vector)` en la consulta pgvector (sin cast, PostgreSQL no infería el tipo).
- Comando de Celery en compose (`app.workers.celery_app:celery_app`).
- Tests que no probaban nada real: `test_pgvector_integration.py` era una copia del de ingesta y `test_chunking.py` reimplementaba la lógica en vez de importarla. Ahora prueban el código real.
- Chunking movido de dentro de la tarea a un módulo testeable, con metadatos de sección y respeto de páginas.
- Parseo real con Docling + fallback (antes solo `pypdf` con contenido inventado en caso de error).
- Gating de evidencia con umbral (antes cualquier resultado del top-k contaba como evidencia).
- Citas inventadas filtradas contra los fragmentos recuperados.

**Revisado manualmente**: idempotencia de la tarea, aislamiento por workspace, validación de archivos, propagación de contexto de tracing y el contrato de salida.

## 8. Riesgos conocidos / siguientes pasos

- Recalibrar `MIN_EVIDENCE_SCORE` con embeddings reales (el valor actual es para mock).
- Añadir OCR para PDFs escaneados.
- Autenticación + workspace derivado del token (hoy lo declara el cliente).
- Métricas de coste reales por proveedor y presupuesto por workspace.
- Test E2E del frontend y eval más amplio (paráfrasis, preguntas multi-documento).
