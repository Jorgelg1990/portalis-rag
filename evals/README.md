# Conjunto de evaluación de recuperación (retrieval eval)

## Corpus

- `manual-aduanas.pdf` — manual operativo de 2 páginas (documentación requerida, inspección, tributos, almacenaje, canales de despacho).
- `generate_sample.py` — regenera el PDF sin dependencias externas: `python evals/generate_sample.py`.

## Preguntas

`questions.json` contiene 6 preguntas: 5 respondibles y 1 fuera de dominio que debe provocar abstención. Cada una define `expected_keywords` y `should_find`.

## Cómo ejecutar la evaluación

Con el stack levantado (`docker compose up --build`):

```bash
# Desde la raíz del repo
python evals/run_eval.py
```

El script:

1. Sube `manual-aduanas.pdf` al workspace `eval`.
2. Espera a que el estado sea `listo` (máx. 5 min).
3. Comprueba aislamiento por tenant: la misma pregunta en el workspace `default` no debe recuperar fragmentos.
4. Lanza las 6 preguntas y valida acción, abstención, citas y keywords esperadas.
5. Devuelve exit code 0 solo si todo pasa.

Opciones:

```bash
python evals/run_eval.py --base-url http://localhost:8000 --workspace eval
```

### Alternativa manual (curl)

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@evals/manual-aduanas.pdf" -F "workspace_id=eval"

curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Qué documentos se requieren para la importación?", "workspace_id": "eval"}'
```

En PowerShell usa `curl.exe` para evitar el alias de `Invoke-WebRequest`.

## Qué se evalúa

| Criterio | Cómo se comprueba |
|---|---|
| Recuperación | `fragments_retrieved > 0` y keywords esperadas presentes en respuesta/citas |
| Citabilidad | cada cita apunta a un `chunk_id` recuperado (el backend descarta citas inventadas) |
| Gating de evidencia | pregunta fuera de dominio → `insufficient_evidence=true`, `action=abstain` |
| Aislamiento | workspace distinto → sin fragmentos, abstención |
| Trazabilidad | `model_used`, `latency_ms`, `trace_id` en la respuesta |

## Resultado esperado

```text
[PASS] aislamiento por workspace: otro workspace no recupera fragmentos (action=abstain)
[PASS] #1 ¿Qué documentos se requieren para la importación?
[PASS] #2 ¿Cuánto dura la inspección aduanera?
[PASS] #3 ¿Cuándo se pagan los tributos?
[PASS] #4 ¿Cuál es el horario del almacén portuario?
[PASS] #5 ¿Qué significa el canal verde?
[PASS] #6 ¿Cuál es la receta de la lasaña de carne?

Resultado: 7/7 comprobaciones correctas
```
