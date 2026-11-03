from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import documents, query
from app.core.tracing import setup_tracing
from app.core.db import engine, Base
import asyncio

app = FastAPI(title="Portalis RAG API", version="1.0.0")

setup_tracing("portalis-rag-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(query.router, prefix="/api", tags=["query"])

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "portalis-rag-api"}
