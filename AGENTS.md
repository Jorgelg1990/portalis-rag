# AGENTS.md

## Project
RAG documental assistant for Portalis Logística. Monorepo: backend (FastAPI), frontend (React), infra (docker-compose). Async ingestion of PDFs/DOCX via Celery+Redis → Docling parsing → chunk with metadata (document/page/section) → embeddings → PostgreSQL+pgvector. Query with verifiable citations, end-to-end traceable.

## Quickstart
- `docker compose up --build` must run full stack
- Must work without real keys: mock/deterministic LLM + embeddings providers
- Flower (or equivalent) in docker-compose to inspect queues/tasks

## Core Requirements
- **API**: FastAPI + strict Pydantic models (upload, ingest status, list docs, query)
- **Ingestion**: Celery+Redis, Docling parsing, chunk metadata (doc/page/section), pgvector storage. Task idempotent + retryable
- **RAG**: retrieve chunks → LiteLLM (primary Gemini, fallback second/provider or simulated) → structured response with verifiable citations
- **Structured output**: Pydantic AI or justified alternative. Must return answer/citations/confidence/insufficient-evidence flag
- **Evidence gating**: consistent behavior when retrieval lacks evidence (answer / abstain / ask clarification)
- **Provider abstraction**: swap LLM without touching business logic

## Observability & Security
- **Tracing**: OpenTelemetry across API → Celery → pgvector retrieval → LLM. Attributes: model, tokens, latency, #fragments. Never log sensitive document content
- **Security**: validate file type/size, secrets via env only, treat docs as untrusted (prompt injection), basic workspace/tenant isolation on queries
- **Errors**: retries w/backoff, handle corrupt/protected docs, states (pendiente/procesando/fallido/listo), timeouts, LLM fallback, consistent API errors

## Testing
- Unit: chunking, prompt construction
- Integration: PostgreSQL+pgvector in container
- Ingestion flow with Celery; LLM simulated in CI
- Small retrieval eval set with sample docs + run instructions
- GitHub Actions must run lint + tests on push

## Frontend
React: file upload, live ingest status (polling/streaming), chat with visible citations, open source fragment

## Deliverables
- Public GitHub monorepo (backend/frontend/infra/docker-compose). Only most recent commit at submission counts
- `README.md`: run instructions (no-keys mode), done/not done, known limitations; include how to use Flower to debug stuck ingestion
- `DECISIONS.md`: chunking/retrieval strategy + eval justification; contradiction/low-evidence handling + UX; provider/cost policy (fallback/tokens/latency/tradeoffs); tracing/logging vs confidentiality; tradeoffs, discarded alternatives, GenAI usage (accepted/corrected)
- Automated tests + retrieval eval set with instructions
- GitHub Actions (lint+tests) + brief description/capture of end-to-end OpenTelemetry trace
