from app.services.chunking import ParsedBlock, chunk_blocks, chunk_pages


def test_chunks_keep_page_and_section_metadata():
    blocks = [
        ParsedBlock("Introducción al régimen aduanero.", page_number=1, section="Introducción"),
        ParsedBlock("Los documentos requeridos son la factura comercial.", page_number=1, section="Introducción"),
        ParsedBlock("Plazos de inspección: 48 horas.", page_number=2, section="Inspección"),
    ]

    chunks = chunk_blocks(blocks, max_chars=800)

    assert len(chunks) == 2
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["section"] == "Introducción"
    assert "factura comercial" in chunks[0]["content"]
    assert chunks[1]["page_number"] == 2
    assert chunks[1]["section"] == "Inspección"
    assert [c["chunk_index"] for c in chunks] == [0, 1]


def test_chunks_never_exceed_max_chars():
    text = "Frase de prueba sobre aduanas. " * 200  # ~5800 chars
    chunks = chunk_blocks([ParsedBlock(text, page_number=1)], max_chars=500)

    assert len(chunks) > 1
    assert all(len(c["content"]) <= 500 for c in chunks)
    assert all(c["page_number"] == 1 for c in chunks)


def test_chunks_split_on_page_boundary():
    blocks = [
        ParsedBlock("Contenido de la página uno.", page_number=1),
        ParsedBlock("Contenido de la página dos.", page_number=2),
    ]
    chunks = chunk_blocks(blocks, max_chars=800)

    assert len(chunks) == 2
    assert chunks[0]["page_number"] == 1
    assert chunks[1]["page_number"] == 2


def test_chunk_pages_wrapper_and_empty_input():
    assert chunk_pages([]) == []
    assert chunk_pages([(3, "Texto de la página tres.")])[0]["page_number"] == 3


def test_oversized_block_has_overlap():
    sentence = "La inspección aduanera se realiza en el recinto portuario. "
    chunks = chunk_blocks([ParsedBlock(sentence * 40, page_number=1)], max_chars=200, overlap_chars=50)

    assert len(chunks) > 1
    # consecutive chunks must share some text (overlap), not lose the boundary
    assert chunks[0]["content"][-20:] in chunks[1]["content"]
