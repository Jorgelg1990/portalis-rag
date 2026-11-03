# Conjunto de Evaluación de Recuperación

## Documentos de ejemplo

- `manual-aduanas.pdf` - Manual operativo con procedimientos de aduanas (documentación requerida, inspección, liquidación)

## Preguntas de evaluación

Ver `questions.json` - incluye preguntas que deben encontrar respuesta y una fuera de dominio para probar el gating de evidencia.

## Cómo ejecutar la evaluación

1. Levantar el stack: `docker compose up --build`
2. Subir el documento de ejemplo:
```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@evals/manual-aduanas.pdf" \
  -F "workspace_id=default"
```
3. Esperar a que el estado pase a `listo` (ver http://localhost:5173 o polling)
4. Hacer las preguntas del conjunto:
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Qué documentos se requieren para la importación?", "workspace_id": "default"}'
```

## Métricas a revisar
- ¿Se recuperan fragmentos relevantes? (ver `fragments_retrieved`)
- ¿Las citas apuntan a documentos correctos? (ver `citations`)
- ¿Hay suficiente evidencia para responder? (`insufficient_evidence`, `confidence`)
- ¿Se abstiene correctamente cuando no hay info? (pregunta fuera de dominio)
- Trazabilidad: revisar spans en logs / descripción de traza OTEL
