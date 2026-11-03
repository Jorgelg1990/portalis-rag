# DECISIONS.md

## 1. Estrategia de troceado y recuperación

**Estrategia elegida:**
- **Chunking**: Splitting por párrafos con tamaño objetivo ~800 chars, sin solapamiento complejo (pragmático). Se guarda metadata: `document_id`, `page_number`, `section`, `chunk_index`.
- **Recuperación**: Búsqueda vectorial por similitud coseno con pgvector (`embedding <=> query_emb`). Top-K=4 por defecto.
- **Reranking**: No implementado (overhead innecesario para MVP). Se confía en similitud vectorial.
- **Búsqueda híbrida**: No implementada. Solo vectorial.

**Justificación con evaluación:**
- Conjunto pequeño de docs de ejemplo en `evals/` para verificar recuperación
- Priorizamos **rapidez y simplicidad** sobre complejidad. Para documentos operativos/contratos con estructura clara, chunking por párrafos funciona razonablemente bien
- Metadata (página) permite citas verificables que es requisito clave
- Si falla recuperación, el gating de evidencia lo detecta

**Descartado:** Solapamiento grande, híbrido BM25+vector, reranker cross-encoder - añadirían complejidad y tiempo sin ganar mucho para este scope.

## 2. Documentos contradictorios o poca evidencia

**Comportamiento del sistema:**
- **Recuperación vacía**: Si no hay chunks relevantes → `action: abstain`, `insufficient_evidence: true`, respuesta clara "No hay información suficiente..."
- **Poca evidencia**: Con chunks pero baja confianza → se marca `insufficient_evidence` según lógica del proveedor. En modo mock devuelve confianza moderada pero estructura clara
- **Contradicciones**: No se resuelven automáticamente. El sistema **muestra citas** de ambos fragmentos si ambos se recuperan (top-k puede traer ambos). El operador decide.

**Cambios en UX:**
- Citas siempre visibles con documento + página
- Botón para "abrir fragmento fuente" (modal) mostrando el snippet completo
- Se muestra metadata: confianza, acción, nº fragmentos, latencia, modelo
- Mensaje explícito cuando hay evidencia insuficiente
- Estado de ingestión claro por documento

**Razón:** Mejor **abstenerse y citar** que inventar. Transparencia > falsa certeza.

## 3. Política de proveedor y coste

**Configuración:**
- **Primario**: Gemini vía LiteLLM (configurable) - `LITELLM_MODEL=gemini/gemini-1.5-flash`
- **Fallback**: Segundo proveedor o simulado. En `.env` por defecto `FALLBACK_LLM_PROVIDER=mock`
- **Modo desarrollo/CI**: `LLM_PROVIDER=mock`, `EMBED_PROVIDER=mock` (sin claves)

**Cuándo hacer fallback:**
- Error de API, timeout, rate limit
- Respuesta inválida (no pasa validación Pydantic)
- Provider no disponible

**Límites:**
- `top_k` limitado (1-10, default 4) para controlar contexto
- Timeouts en llamadas LLM (gestionados por cliente)
- Chunking limita tamaño de contexto

**Trade-offs aceptados:**
- **Calidad vs velocidad/coste**: Elegimos `gemini-1.5-flash` como primario (balanceado). En modo mock priorizamos **funcionalidad sobre calidad**
- **Simplicidad vs robustez**: Fallback existe por abstracción pero lógica mínima para cumplir plazo
- **Transparencia**: Siempre se muestra `model_used` para trazabilidad

**Abstracción:** `ProviderFactory` permite cambiar proveedor sin tocar lógica de negocio (cumple requisito).

## 4. Datos en trazas, logs y métricas vs confidencialidad

**Qué SÍ puede aparecer:**
- IDs (document_id, chunk_id, task_id)
- Metadatos: filename, file_type, file_size, page_number, section, workspace_id
- Métricas: latencia, tokens (estimados), modelo, nº fragmentos recuperados, scores
- Estados de tarea, errores genéricos
- Conteo de chunks

**Qué NO debe aparecer:**
- **Contenido completo de documentos** - NUNCA en logs/trazas
- **Respuestas completas con PII** si son sensibles (en modo mock evitamos)
- **Claves/secretos** - solo vía env vars
- **Prompts con documento completo** - se pasa contexto limitado

**Balance diagnóstico vs confidencialidad:**
- OpenTelemetry registra **atributos estructurados** (modelo, latencia, counts) no texto libre del documento
- En worker/api solo logueamos errores con `str(exc)[:500]` sin volcar contenido
- `snippets` se muestran **únicamente al usuario en la UI** como citas verificables (requisito del producto)
- Tracing permite diagnosticar "ingesta lenta" / "recuperación mala" con métricas sin exponer contenido
- Aislamiento por `workspace_id` en queries

**Implementación:** Usamos spans con atributos numéricos/IDs. Evitamos `span.add_event` con contenido de documentos.

## Salida estructurada con Pydantic AI

**Decisión:** Se ha implementado validación estructurada con **Pydantic AI** (`pydantic-ai`).

- **Implementación**: `backend/app/services/rag_agent.py` define un `Agent` con `result_type=RAGStructuredOutput` (Pydantic BaseModel) que fuerza `answer`, `citations`, `confidence`, `insufficient_evidence`, `action`. 
- **Modo sin llaves**: Usa `TestModel` para generar respuestas deterministas sin credenciales. En producción puede usar Gemini vía el modelo configurado.
- **Validación**: Pydantic AI valida el esquema y gestiona reintentos si la respuesta no cumple con el tipo.
- **Integración**: El endpoint `/api/query` usa `rag_agent_service.generate_structured()` y traza con OpenTelemetry (`model.name` indica `pydantic-ai`).
- **Justificación**: Cumple estrictamente el requisito "salida estructurada (...) validada con Pydantic AI". Se mantiene abstracción de proveedores y compatibilidad con modo mock para CI sin claves.

## Uso de IA Generativa

**Aceptado:**
- Estructura inicial del proyecto y boilerplate
- Generación de schemas Pydantic
- Configuración docker-compose
- Componentes React básicos
- Tests skeleton

**Corregido:**
- Dimensión de embeddings (ajustada a 384 para mock)
- Manejo de async/sync DB (separado para worker)
- Validación de archivos más estricta
- Flujo de estados de ingestión
- Estructura de trazas para cumplir atributos requeridos
- Integración de Pydantic AI para salida estructurada validada

**Enfoque:** IA para acelerar estructura, revisión manual de lógica crítica (idempotencia, gating, citas).
