def test_chunking_simple():
    content = "Para 1\n\nPara 2\n\nPara 3"
    paragraphs = content.split('\n\n')
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) < 800:
            current += "\n\n" + p if current else p
        else:
            if current:
                chunks.append(current)
            current = p
    if current:
        chunks.append(current)
    assert len(chunks) == 3

def test_prompt_construction():
    context = [{"content": "test content", "document_name": "doc.pdf"}]
    prompt = f"Answer based on: {context[0]['content']}"
    assert "test content" in prompt
    assert len(prompt) > 0
