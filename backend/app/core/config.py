from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    app_name: str = "portalis-rag"
    env: str = "dev"
    secret_key: str = "dev-secret"
    upload_dir: str = "/app/uploads"
    max_upload_mb: int = 50
    allowed_exts: str = "pdf,docx"

    # Dev defaults keep the app importable without a .env file.
    # docker-compose overrides these with service names (db, redis).
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/portalis"
    sync_database_url: str = "postgresql://postgres:postgres@localhost:5432/portalis"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    llm_provider: str = "mock"
    embed_provider: str = "mock"
    litellm_model: str = "gemini/gemini-1.5-flash"
    fallback_llm_provider: str = "mock"
    fallback_litellm_model: str = "gpt-4o-mini"
    embedding_model: str = "gemini/text-embedding-004"
    embedding_dim: int = 384

    # Minimum cosine similarity for a fragment to count as evidence.
    min_evidence_score: float = 0.12

    # Parser: docling (primary) with automatic pypdf fallback.
    parser: str = "docling"
    chunk_max_chars: int = 800

    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "portalis-rag"

    default_workspace_id: str = "default"

    @property
    def allowed_extensions(self) -> List[str]:
        return [ext.strip().lower() for ext in self.allowed_exts.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
