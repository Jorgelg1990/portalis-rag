from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, query
from app.core.db import engine, Base
from app.core.tracing import setup_tracing
# Imported for Base.metadata.create_all (table registration).
from app.models import chunk, document  # noqa: F401

tracer = setup_tracing("portalis-rag-api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Portalis RAG API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(query.router, prefix="/api", tags=["query"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "portalis-rag-api"}
