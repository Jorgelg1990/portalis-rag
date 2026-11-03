from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID

class Citation(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_name: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    snippet: str
    score: float

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3)
    workspace_id: str = Field(default="default")
    top_k: int = Field(default=4, ge=1, le=10)

class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    confidence: float = Field(ge=0, le=1)
    insufficient_evidence: bool
    action: str  # answer | abstain | ask_clarification
    model_used: str
    latency_ms: float
    fragments_retrieved: int
    trace_id: Optional[str] = None
