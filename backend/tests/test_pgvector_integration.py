import os

import pytest
from sqlalchemy import create_engine, text


def _sync_url() -> str:
    url = os.environ.get("SYNC_DATABASE_URL") or "postgresql://postgres:postgres@localhost:5432/test_db"
    if url.startswith("postgresql+asyncpg"):
        url = url.replace("postgresql+asyncpg", "postgresql")
    return url


@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(_sync_url(), future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # no DB available (local run without docker)
        pytest.skip(f"PostgreSQL no disponible: {exc}")
    yield engine
    engine.dispose()


def test_pgvector_similarity_search(pg_engine):
    """Integración real contra PostgreSQL + pgvector (no sqlite)."""
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
        conn.execute(text("DROP TABLE IF EXISTS test_chunks_pgvector"))
        conn.execute(
            text(
                "CREATE TABLE test_chunks_pgvector ("
                "id uuid PRIMARY KEY DEFAULT uuid_generate_v4(), "
                "content text NOT NULL, "
                "embedding vector(3) NOT NULL)"
            )
        )
        # two vectors: one identical to the query, one orthogonal
        conn.execute(
            text(
                "INSERT INTO test_chunks_pgvector (content, embedding) VALUES "
                "('fragmento relevante', '[1,0,0]'), "
                "('fragmento irrelevante', '[0,1,0]')"
            )
        )

        row = conn.execute(
            text(
                "SELECT content, 1 - (embedding <=> '[1,0,0]'::vector) AS score "
                "FROM test_chunks_pgvector "
                "ORDER BY embedding <=> '[1,0,0]'::vector "
                "LIMIT 1"
            )
        ).first()

        assert row is not None
        assert row[0] == "fragmento relevante"
        assert float(row[1]) == pytest.approx(1.0, abs=1e-6)

        conn.execute(text("DROP TABLE test_chunks_pgvector"))
