from app.rag import ExtractiveAnswer, HashEmbedding, sections_from_text


def test_markdown_headings_become_citation_sections():
    sections = sections_from_text("# Uno\n\nPrima frase.\n\n# Due\n\nSeconda frase.", ".md")
    assert sections == [("Uno", "Prima frase."), ("Due", "Seconda frase.")]


def test_embedding_is_repeatable_and_normalized():
    provider = HashEmbedding()
    first = provider.embed("Rimborso spese viaggio")
    assert first == provider.embed("Rimborso spese viaggio")
    assert abs(sum(value * value for value in first) - 1) < 0.001


def test_answer_quotes_only_evidence():
    evidence = [{"document_id": "one", "title": "Trasferte", "section": "Hotel", "content": "Il limite per un hotel è 140 euro per notte.", "similarity": 0.8}]
    answer, citations = ExtractiveAnswer().answer("Qual è il limite per un hotel per notte?", evidence)
    assert "140 euro" in answer
    assert citations[0]["quote"] == answer
    assert citations[0]["section"] == "Hotel"


def test_abstains_if_evidence_does_not_support_question():
    evidence = [{"document_id": "one", "title": "Trasferte", "section": "Hotel", "content": "Il limite per un hotel è 140 euro per notte.", "similarity": 0.8}]
    answer, citations = ExtractiveAnswer().answer("Qual è il colore del logo aziendale?", evidence)
    assert citations == []
    assert answer.startswith("Non posso rispondere")
