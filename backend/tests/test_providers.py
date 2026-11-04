"""Provider abstraction: deterministic embeddings and no-keys LLM."""

import math

from app.services.providers import MockEmbeddings, MockLLM, ProviderFactory, tokenize


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def test_mock_embeddings_are_deterministic_and_sized():
    embedder = MockEmbeddings()
    first = embedder.embed_texts(["documentos de importación"])[0]
    second = embedder.embed_texts(["documentos de importación"])[0]

    assert first == second
    assert len(first) == 384
    assert abs(math.sqrt(sum(v * v for v in first)) - 1.0) < 1e-6


def test_mock_embeddings_rank_related_text_higher():
    embedder = MockEmbeddings()
    query = embedder.embed_query("¿Qué documentos se requieren para la importación?")
    relevant = embedder.embed_query("Los documentos requeridos para la importación son la factura comercial.")
    irrelevant = embedder.embed_query("La receta de lasaña lleva tomate y carne picada.")

    assert _cosine(query, relevant) > _cosine(query, irrelevant)
    assert _cosine(query, relevant) > 0.15


def test_tokenizer_drops_stopwords():
    assert "de" not in tokenize("manual de aduanas")
    assert "aduanas" in tokenize("manual de aduanas")


def test_mock_llm_abstains_without_context():
    result = MockLLM().generate("pregunta", [])

    assert result["insufficient_evidence"] is True
    assert result["action"] == "abstain"


def test_mock_llm_cites_retrieved_fragments():
    context = [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "document_name": "manual.pdf",
            "content": "La inspección dura 48 horas.",
            "page_number": 4,
            "section": "Plazos",
        }
    ]
    result = MockLLM().generate("¿Cuánto dura?", context)

    assert result["action"] == "answer"
    assert result["citations"][0]["chunk_id"] == "c1"
    assert "48 horas" in result["answer"]


def test_factory_returns_mock_in_no_keys_mode():
    assert isinstance(ProviderFactory.get_embeddings(), MockEmbeddings)
    assert isinstance(ProviderFactory.get_llm(), MockLLM)
